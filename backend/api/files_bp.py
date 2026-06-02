"""
Paper-files blueprint — list / upload / delete / preview / serve raw.
Auth modes for /raw mirror app.py: Bearer header, signed token (?s=), or
legacy ?t=jwt. Cookies travel automatically because JWT_TOKEN_LOCATION
includes both cookies and headers.
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
    verify_jwt_in_request,
)

from core import s3_storage
from database.models import Paper, PaperFile, db
from paper_generation.utils import (
    PAPER_ID_RE,
    safe_paper_dir,
    upload_folder,
    verify_resource_token,
)

log = logging.getLogger(__name__)

files_bp = Blueprint("paper_files", __name__, url_prefix="/api/papers")

ALLOWED_FILE_EXTS = {".pdf", ".docx", ".doc", ".txt", ".md", ".xlsx", ".xls", ".csv"}
# Per-file size cap. Reference papers (esp. scanned PDFs from journals) easily
# breach 10 MB; cap raised to 30 MB so users don't get rejected for normal
# academic PDFs. The whole multipart payload is still bounded by Flask's
# MAX_CONTENT_LENGTH (60 MB by default).
MAX_FILE_BYTES = 30 * 1024 * 1024
MAX_PREVIEW_CHARS = 20_000

# Magic bytes for file type validation (first few bytes of file)
FILE_SIGNATURES = {
    ".pdf": [b"%PDF"],
    ".docx": [b"PK\x03\x04"],  # ZIP format
    ".doc": [b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"],  # OLE2 format
    ".xlsx": [b"PK\x03\x04"],  # ZIP format
    ".xls": [b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"],  # OLE2 format
    ".txt": None,  # No signature check for plain text
    ".md": None,
    ".csv": None,
}

# Shared extraction pool. Capped at 20 — fitz/openpyxl/python-docx are CPU-bound
# but release the GIL on heavy work, and we never want a single user to spawn
# more than 20 simultaneous extractions across the whole process.
_EXTRACT_POOL = ThreadPoolExecutor(max_workers=20, thread_name_prefix="pdf-extract")


def _validate_file_content(data: bytes, ext: str) -> bool:
    """Validate file content matches expected type using magic bytes.
    Returns True if valid, False if content doesn't match extension.
    """
    signatures = FILE_SIGNATURES.get(ext)
    if signatures is None:
        return True

    if not data:
        return False

    for sig in signatures:
        if data.startswith(sig):
            return True

    return False


def _read_file_with_limit(stream, max_bytes: int) -> tuple[bytes | None, str | None]:
    """Read file stream with size limit. Returns (data, error_msg).
    Prevents memory exhaustion by checking size before reading entire file.
    """
    chunk_size = 8192
    chunks = []
    total_size = 0

    try:
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break

            total_size += len(chunk)
            if total_size > max_bytes:
                return None, f"File exceeds {max_bytes // (1024 * 1024)}MB limit"

            chunks.append(chunk)

        return b"".join(chunks), None
    except Exception as e:
        log.warning("file_read_error", extra={"err": str(e)})
        return None, "Failed to read file"


def _extract_text_for_preview(filepath: Path, ext: str) -> str:
    """Best-effort plain-text extraction. PDF prefers PyMuPDF (fitz) for
    layout-aware output; Excel uses openpyxl multi-sheet flatten; DOCX uses
    python-docx with table/paragraph traversal so cells aren't dropped.
    rofiq.txt #6: 'extraksi ke text yang presisi'.
    """
    try:
        if ext == ".pdf":
            try:
                import fitz  # PyMuPDF — better fidelity than pdfminer for tables

                parts = []
                with fitz.open(str(filepath)) as doc:
                    for page in doc:
                        parts.append(page.get_text("text"))
                        if sum(len(p) for p in parts) >= MAX_PREVIEW_CHARS:
                            break
                txt = "\n\n".join(parts)
                if txt.strip():
                    return txt[:MAX_PREVIEW_CHARS]
            except Exception:
                pass
            from paper_generation.extract_pdfs import extract_text_from_pdf

            with open(filepath, "rb") as f:
                txt = extract_text_from_pdf(f)
            return txt[:MAX_PREVIEW_CHARS]

        if ext in (".docx", ".doc"):
            try:
                from docx import Document

                doc = Document(str(filepath))
                chunks: list[str] = []
                for p in doc.paragraphs:
                    if p.text.strip():
                        chunks.append(p.text)
                for tbl in doc.tables:
                    for row in tbl.rows:
                        cells = [c.text.strip() for c in row.cells]
                        if any(cells):
                            chunks.append(" | ".join(cells))
                txt = "\n".join(chunks).strip()
                if txt:
                    return txt[:MAX_PREVIEW_CHARS]
            except Exception as e:
                # python-docx fails on .docx files with missing/extra relationships
                # (we've seen this with files exported by Pages, LibreOffice, and
                # some Word web variants). Fallback: parse word/document.xml from
                # the zip directly. Loses table structure but keeps paragraph
                # text, which is what the AI actually consumes.
                log.info(
                    "docx_fallback",
                    extra={"file": str(filepath), "err": str(e)[:200]},
                )
            try:
                import zipfile

                import defusedxml.ElementTree as ET

                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                with zipfile.ZipFile(str(filepath)) as zf:
                    candidates = [
                        n
                        for n in zf.namelist()
                        if n.endswith("/document.xml") or n == "word/document.xml"
                    ]
                    if not candidates:
                        return ""
                    with zf.open(candidates[0]) as raw:
                        tree = ET.parse(raw)
                lines: list[str] = []
                for para in tree.iter(f"{{{ns['w']}}}p"):
                    parts = [(t.text or "") for t in para.iter(f"{{{ns['w']}}}t")]
                    line = "".join(parts).strip()
                    if line:
                        lines.append(line)
                return "\n".join(lines)[:MAX_PREVIEW_CHARS]
            except Exception as e2:
                log.info(
                    "docx_zip_fallback_failed",
                    extra={"file": str(filepath), "err": str(e2)[:200]},
                )
                return ""

        if ext in (".xlsx", ".xls"):
            from openpyxl import load_workbook

            wb = load_workbook(str(filepath), read_only=True, data_only=True)
            out: list[str] = []
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                out.append(f"# Sheet: {sheet_name}")
                row_count = 0
                for row in ws.iter_rows(values_only=True):
                    cells = ["" if v is None else str(v) for v in row]
                    if any(cells):
                        out.append("\t".join(cells))
                    row_count += 1
                    if row_count >= 500:  # cap per sheet to keep extraction fast
                        out.append("... (truncated)")
                        break
                out.append("")
                if sum(len(s) for s in out) >= MAX_PREVIEW_CHARS:
                    break
            return "\n".join(out)[:MAX_PREVIEW_CHARS]

        if ext == ".csv":
            # BUG FIX: Add size check before reading CSV to prevent memory exhaustion
            if filepath.stat().st_size > MAX_FILE_BYTES:
                return f"[CSV file too large: {filepath.stat().st_size // (1024*1024)}MB, preview skipped]"
            return filepath.read_text(encoding="utf-8", errors="replace")[:MAX_PREVIEW_CHARS]

        if ext in (".txt", ".md"):
            return filepath.read_text(encoding="utf-8", errors="replace")[:MAX_PREVIEW_CHARS]
    except Exception as e:
        log.info("extract_failed", extra={"file": str(filepath), "ext": ext, "err": str(e)})
        return ""
    return ""


@files_bp.route("/<paper_id>/files", methods=["GET"])
@jwt_required()
def list_paper_files(paper_id: str):
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404
    files = PaperFile.query.filter_by(paper_id=paper_id).order_by(PaperFile.created_at.desc()).all()
    return jsonify({"files": [f.to_dict() for f in files]})


@files_bp.route("/<paper_id>/files", methods=["POST"])
@jwt_required()
def upload_paper_files(paper_id: str):
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files uploaded"}), 400

    # Phase 1: read bytes, validate, and persist (S3 or local disk)
    accepted: list[dict] = []
    warnings: list[str] = []
    temp_files: list[Path] = []  # Track temp files for cleanup

    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in ALLOWED_FILE_EXTS:
            warnings.append(f"{f.filename}: format tidak didukung")
            continue

        # Read with size limit to prevent memory exhaustion
        data, error = _read_file_with_limit(f.stream, MAX_FILE_BYTES)
        if error:
            warnings.append(f"{f.filename}: {error}")
            continue

        if not data:
            warnings.append(f"{f.filename}: file kosong")
            continue

        # Validate file content matches extension (magic bytes check)
        if not _validate_file_content(data, ext):
            warnings.append(
                f"{f.filename}: konten file tidak sesuai dengan ekstensi (kemungkinan file berbahaya)"
            )
            continue

        name = f"{uuid.uuid4().hex}{ext}"
        s3_key = f"{paper_id}/files/{name}"

        # Determine MIME type for S3
        mime_map = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".csv": "text/csv",
            ".txt": "text/plain",
            ".md": "text/markdown",
        }
        content_type = mime_map.get(ext, "application/octet-stream")

        # Upload to S3 or save locally
        if s3_storage.is_s3_enabled():
            # Upload to S3
            if not s3_storage.upload_file(data, s3_key, content_type):
                warnings.append(f"{f.filename}: gagal upload ke S3")
                continue

            # Create temp file for text extraction
            temp_file = Path(tempfile.mktemp(suffix=ext))
            temp_file.write_bytes(data)
            temp_files.append(temp_file)
            filepath = temp_file
        else:
            # Save to local filesystem (original behavior)
            paper_dir = safe_paper_dir(paper_id)
            if not paper_dir:
                warnings.append(f"{f.filename}: Invalid paper id")
                continue
            files_dir = paper_dir / "files"
            files_dir.mkdir(parents=True, exist_ok=True)
            filepath = files_dir / name
            filepath.write_bytes(data)

        accepted.append(
            {
                "name": name,
                "filepath": filepath,
                "ext": ext,
                "original_name": (f.filename or "")[:255],
                "size": len(data),
                "s3_key": s3_key,
            }
        )

    if not accepted:
        # Clean up temp files
        for temp_file in temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception:
                pass
        return jsonify({"success": True, "files": [], "warnings": warnings})

    # Phase 2: extract text in parallel via the shared 20-worker pool. Each call
    # is independent and DB-free; we collect texts then commit in one batch.
    futures = [
        (item, _EXTRACT_POOL.submit(_extract_text_for_preview, item["filepath"], item["ext"]))
        for item in accepted
    ]

    saved = []
    try:
        for item, fut in futures:
            try:
                extracted = fut.result(timeout=30)
            except Exception as e:
                log.info("extract_failed", extra={"file": item["name"], "err": str(e)})
                extracted = ""

            # Store S3 key or local path depending on storage mode
            file_path = item["s3_key"] if s3_storage.is_s3_enabled() else f"{paper_id}/files/{item['name']}"

            entry = PaperFile(
                paper_id=paper_id,
                user_id=user_id,
                filename=item["name"],
                original_name=item["original_name"],
                ext=item["ext"],
                size_bytes=item["size"],
                file_path=file_path,
                extracted_text=extracted,
            )
            db.session.add(entry)
            db.session.flush()
            # Include extracted text so the chat upload path can inline it
            # into the user's message in one round trip. The Files-tab UI
            # ignores this field — it calls /preview on demand.
            saved.append(entry.to_dict(include_text=True))

        db.session.commit()

        # Clean up temp files after successful commit
        for temp_file in temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception:
                log.warning("upload_paper_files: could not clean up temp file %s", temp_file)

        return jsonify({"success": True, "files": saved, "warnings": warnings})
    except Exception:
        db.session.rollback()
        # Clean up on failure
        for item in accepted:
            try:
                # Delete from S3 if uploaded
                if s3_storage.is_s3_enabled():
                    s3_storage.delete_file(item["s3_key"])
                # Delete local file if exists
                elif item["filepath"].exists():
                    item["filepath"].unlink()
            except Exception:
                log.warning("upload_paper_files: could not clean up %s", item["filepath"])

        # Clean up temp files
        for temp_file in temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception:
                pass

        log.exception("upload_paper_files failed (rolled back)", extra={"paper_id": paper_id})
        return jsonify({"error": "Upload failed"}), 500


@files_bp.route("/<paper_id>/files/<int:file_id>", methods=["DELETE"])
@jwt_required()
def delete_paper_file(paper_id: str, file_id: int):
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    entry = PaperFile.query.filter_by(id=file_id, paper_id=paper_id, user_id=user_id).first()
    if not entry:
        return jsonify({"error": "File not found"}), 404

    filepath = upload_folder() / entry.file_path
    try:
        if filepath.exists():
            filepath.unlink()
    except Exception:
        log.warning("delete_paper_file: could not unlink %s", filepath)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({"success": True})


@files_bp.route("/<paper_id>/files/<int:file_id>/raw", methods=["GET"])
def serve_paper_file(paper_id: str, file_id: int):
    """Serve original file. Auth: Bearer/cookie, ?s=signed, or legacy ?t=jwt."""
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400

    signed = request.args.get("s")
    if signed:
        uid = verify_resource_token(signed, f"file:{paper_id}", str(file_id))
        if not uid:
            return jsonify({"error": "Unauthorized"}), 401
        user_id = uid
    else:
        try:
            verify_jwt_in_request()
        except Exception:
            return jsonify({"error": "Unauthorized"}), 401
        try:

            user_id = int(get_jwt_identity())

        except (ValueError, TypeError):

            return jsonify({"error": "Invalid user identity"}), 401

    entry = PaperFile.query.filter_by(id=file_id, paper_id=paper_id, user_id=user_id).first()
    if not entry:
        return jsonify({"error": "File not found"}), 404

    paper_dir = safe_paper_dir(paper_id)
    if not paper_dir:
        return jsonify({"error": "Invalid path"}), 400
    filepath = (paper_dir / "files" / entry.filename).resolve()
    try:
        filepath.relative_to(paper_dir.resolve())
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400
    if not filepath.is_file():
        return jsonify({"error": "File not found"}), 404

    mime_map = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        # BUG FIX: Add missing MIME types for Excel and CSV
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".csv": "text/csv; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
    }
    inline_ok = entry.ext == ".pdf"  # arbitrary uploads inline can become XSS surfaces
    return send_file(
        str(filepath),
        mimetype=mime_map.get(entry.ext, "application/octet-stream"),
        as_attachment=not inline_ok,
        download_name=entry.original_name,
    )


@files_bp.route("/<paper_id>/files/<int:file_id>/preview", methods=["GET"])
@jwt_required()
def preview_paper_file(paper_id: str, file_id: int):
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    entry = PaperFile.query.filter_by(id=file_id, paper_id=paper_id, user_id=user_id).first()
    if not entry:
        return jsonify({"error": "File not found"}), 404
    return jsonify(
        {
            "id": entry.id,
            "ext": entry.ext,
            "original_name": entry.original_name,
            "text": entry.extracted_text or "",
            "raw_url": f"/api/papers/{paper_id}/files/{file_id}/raw",
        }
    )
