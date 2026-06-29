"""
Paper-files blueprint — list / upload / delete / preview / serve raw.
Auth modes for /raw mirror app.py: Bearer header, signed token (?s=), or
legacy ?t=jwt. Cookies travel automatically because JWT_TOKEN_LOCATION
includes both cookies and headers.
"""

from __future__ import annotations

import logging
import re
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
    verify_jwt_in_request,
)

from utils.core import s3_storage
from utils.database.models import Paper, PaperFile, db, safe_commit
from tools.editor.utils import (
    PAPER_ID_RE,
    safe_paper_dir,
    upload_folder,
    verify_resource_token,
)

log = logging.getLogger(__name__)

files = Blueprint("files", __name__, url_prefix="/api/papers")

ALLOWED_FILE_EXTS = {".pdf", ".docx", ".doc", ".txt", ".md", ".xlsx", ".xls", ".csv", ".pptx", ".ppt"}
# 100MB per file — sufficient for large PDFs and scanned documents,
# prevents DoS via memory/disk exhaustion from giant files.
MAX_FILE_BYTES = 100 * 1024 * 1024  # 100MB
MAX_PREVIEW_CHARS = 10_000_000  # No truncation — full PDF text extraction

# Magic bytes for file type validation (first few bytes of file)
FILE_SIGNATURES = {
    ".pdf": [b"%PDF"],
    ".docx": [b"PK\x03\x04"],  # ZIP format
    ".doc": [b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"],  # OLE2 format
    ".xlsx": [b"PK\x03\x04"],  # ZIP format
    ".xls": [b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"],  # OLE2 format
    ".pptx": [b"PK\x03\x04"],  # ZIP format
    ".ppt": [b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"],  # OLE2 format
    ".txt": None,  # No signature check for plain text
    ".md": None,
    ".csv": None,
}

# Shared extraction pool. Capped at 20 — fitz/openpyxl/python-docx are CPU-bound
# but release the GIL on heavy work, and we never want a single user to spawn
# more than 20 simultaneous extractions across the whole process.
_EXTRACT_POOL = ThreadPoolExecutor(max_workers=20, thread_name_prefix="pdf-extract")
import atexit; atexit.register(lambda: _EXTRACT_POOL.shutdown(wait=True))


def _sanitize_text(text: str) -> str:
    """Strip NUL (0x00) and other PostgreSQL-banned control characters
    from extracted text to prevent 'A string literal cannot contain NUL'
    errors on commit."""
    if not text:
        return text
    # NUL (0x00), SOH (0x01), STX (0x02), ETX (0x03), EOT (0x04),
    # ENQ (0x05), ACK (0x06), BEL (0x07), BS (0x08)
    banned = "".join(chr(c) for c in range(0x09))
    return text.translate(str.maketrans("", "", banned))


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
    """Best-effort plain-text extraction via file_extractor module."""
    try:
        from tools.File.file_extractor import extract_to_markdown, MAX_EXTRACT_CHARS
        text = extract_to_markdown(filepath, max_chars=MAX_PREVIEW_CHARS)
        return text or ""
    except Exception as e:
        log.warning("extract_failed", extra={"file": str(filepath), "err": str(e)})
        return ""


def _extract_pdf_metadata(filepath: Path) -> dict:
    """Extract structured metadata from a PDF while it's still on disk.
    Called during upload before raw binary is deleted.
    Returns dict with title, authors, doi, year, abstract, venue, publisher.
    """
    try:
        from tools.Literatur.pdf_metadata_extractor import extract_metadata_from_pdf
        return extract_metadata_from_pdf(filepath)
    except Exception as e:
        log.warning("metadata_extract_failed", extra={"file": str(filepath), "err": str(e)})
        return {}


@files.route("/<paper_id>/files", methods=["GET"])
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
        # Create minimal record so file listing doesn't 404
        paper = Paper(id=paper_id, user_id=user_id, title="Untitled", data={"language": "id"})
        db.session.add(paper)
        db.session.commit()
    files = PaperFile.query.filter_by(paper_id=paper_id).order_by(PaperFile.created_at.desc()).all()
    return jsonify({"files": [f.to_dict() for f in files]})


@files.route("/<paper_id>/files", methods=["POST"])
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
        # Auto-create paper so upload always works even if paper wasn't saved to DB yet
        paper = Paper(id=paper_id, user_id=user_id, title="Untitled", data={"language": "id"})
        db.session.add(paper)
        db.session.commit()

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
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".ppt": "application/vnd.ms-powerpoint",
            ".csv": "text/csv",
            ".txt": "text/plain",
            ".md": "text/markdown",
        }
        content_type = mime_map.get(ext, "application/octet-stream")

        # Upload to S3 or use temp file for extraction
        if s3_storage.is_s3_enabled():
            # Upload to S3
            if not s3_storage.upload_file(data, s3_key, content_type):
                warnings.append(f"{f.filename}: gagal upload ke S3")
                continue

        # Always use temp file — raw binary is NOT persisted to disk.
        # Only extracted .txt text is saved permanently.
        temp_file = Path(tempfile.mktemp(suffix=ext))
        temp_file.write_bytes(data)
        temp_files.append(temp_file)
        filepath = temp_file

        # Raw binary tidak disimpan ke user storage — hanya txt-nya nanti
        # (user_storage save dihapus, hanya save txt setelah extract)

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
            except Exception as _e:
                log.warning("upload_paper_files: could not clean temp %s: %s", temp_file, _e)
        return jsonify({"success": True, "files": [], "warnings": warnings})

    # Phase 2: extract text + metadata in parallel via the shared 20-worker pool.
    # Each call is independent and DB-free; we collect results then commit in one batch.
    futures = []
    for item in accepted:
        text_future = _EXTRACT_POOL.submit(_extract_text_for_preview, item["filepath"], item["ext"])
        # Also extract PDF metadata while file is still on disk
        meta_future = None
        if item["ext"].lstrip(".").lower() == "pdf":
            meta_future = _EXTRACT_POOL.submit(_extract_pdf_metadata, item["filepath"])
        futures.append((item, text_future, meta_future))

    saved = []
    try:
        for item, text_fut, meta_fut in futures:
            try:
                extracted = text_fut.result(timeout=1800)
            except Exception as e:
                log.info("extract_failed", extra={"file": item["name"], "err": str(e)})
                extracted = ""
            # Sanitize to prevent NUL bytes from causing PostgreSQL commit failures
            if extracted:
                extracted = _sanitize_text(extracted)

            # Extract metadata result
            meta = {}
            if meta_fut is not None:
                try:
                    meta = meta_fut.result(timeout=1800)
                except Exception as e:
                    log.info("meta_extract_failed", extra={"file": item["name"], "err": str(e)})

            # Save extracted text as .txt to paper dir: user/<username>/<paper_id>/files/
            if extracted:
                try:
                    _pd = safe_paper_dir(paper_id, user_id=user_id)
                    if _pd:
                        files_dir = _pd / "files"
                        files_dir.mkdir(parents=True, exist_ok=True)
                        txt_name = Path(item["original_name"]).stem + ".txt"
                        safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', txt_name).strip(" ._-") or "extracted"
                        txt_path = files_dir / safe_name
                        with open(txt_path, "w", encoding="utf-8") as fh:
                            fh.write(extracted)
                except Exception as _e:
                    log.warning("upload_paper_files: save extracted txt failed for %s: %s", item["original_name"], _e)

            # Store S3 key or local path depending on storage mode
            # file_path is empty because raw binary is deleted after extraction.
            # Only extracted_text is persisted.
            file_path = ""

            # Serialize metadata authors list to JSON string
            import json as _json
            meta_authors_json = _json.dumps(meta.get("authors") or []) if meta else ""

            # Upsert: if a PaperFile with the same original_name already
            # exists for this paper, update it instead of creating a
            # duplicate (same source file → idempotent extraction).
            entry = PaperFile.query.filter_by(
                paper_id=paper_id,
                user_id=user_id,
                original_name=item["original_name"][:255],
            ).first()
            if entry:
                entry.filename = item["name"]
                entry.ext = item["ext"]
                entry.size_bytes = item["size"]
                entry.file_path = file_path
                entry.extracted_text = extracted
                # Store extracted metadata
                if meta:
                    entry.meta_title = (meta.get("title") or "")[:5000]
                    entry.meta_authors = meta_authors_json[:5000]
                    entry.meta_doi = (meta.get("doi") or "")[:500]
                    entry.meta_year = meta.get("year")
                    entry.meta_abstract = (meta.get("abstract") or "")[:10000]
                    entry.meta_venue = (meta.get("venue") or "")[:500]
                    entry.meta_publisher = (meta.get("publisher") or "")[:500]
            else:
                entry = PaperFile(
                    paper_id=paper_id,
                    user_id=user_id,
                    filename=item["name"],
                    original_name=item["original_name"],
                    ext=item["ext"],
                    size_bytes=item["size"],
                    file_path=file_path,
                    extracted_text=extracted,
                    # Store extracted metadata
                    meta_title=(meta.get("title") or "")[:5000] if meta else "",
                    meta_authors=meta_authors_json[:5000] if meta else "",
                    meta_doi=(meta.get("doi") or "")[:500] if meta else "",
                    meta_year=meta.get("year") if meta else None,
                    meta_abstract=(meta.get("abstract") or "")[:10000] if meta else "",
                    meta_venue=(meta.get("venue") or "")[:500] if meta else "",
                    meta_publisher=(meta.get("publisher") or "")[:500] if meta else "",
                )
                db.session.add(entry)
            db.session.flush()
            
            # Include extracted text so the chat upload path can inline it
            # into the user's message in one round trip. The Files-tab UI
            # ignores this field — it calls /preview on demand.
            saved.append(entry.to_dict(include_text=True))

        safe_commit()

        # Delete raw binary temp files — only extracted text is persisted.
        for item in accepted:
            try:
                if s3_storage.is_s3_enabled():
                    s3_storage.delete_file(item["s3_key"])
                if item["filepath"].exists():
                    item["filepath"].unlink()
            except Exception:
                log.warning("upload_paper_files: could not clean raw %s", item["filepath"])
        # Clean up remaining temp files
        for temp_file in temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception:
                log.warning("upload_paper_files: could not clean up temp file %s", temp_file)

        # Update status.json AFTER successful commit (prevents NameError on entry.id)
        _pd = safe_paper_dir(paper_id, user_id=user_id)
        if _pd:
            try:
                import json as _json2
                status_path = _pd / "status.json"
                status = {}
                if status_path.exists():
                    try:
                        status = _json2.loads(status_path.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                if "files" not in status:
                    status["files"] = []
                files_dir = _pd / "files"
                existing_names = {fe.get("filename") for fe in status["files"]}
                for s in saved:
                    orig = s.get("original_name", "")
                    txt_name = Path(orig).stem + ".txt"
                    safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', txt_name).strip(" ._-") or "extracted"
                    txt_path = files_dir / safe_name
                    if safe_name not in existing_names and txt_path.exists():
                        status["files"].append({
                            "filename": safe_name,
                            "path": str(txt_path),
                            "original_name": orig,
                            "file_id": s.get("id"),
                            "uploaded_at": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
                        })
                        existing_names.add(safe_name)
                status_path.write_text(_json2.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                log.warning("upload_paper_files: status.json update failed", extra={"paper_id": paper_id})

        return jsonify({"success": True, "files": saved, "warnings": warnings})
    except Exception:
        db.session.rollback()
        # Clean up on failure
        for item in accepted:
            try:
                # Delete from S3 if uploaded
                if s3_storage.is_s3_enabled():
                    s3_storage.delete_file(item["s3_key"])
                # Delete temp file if exists
                if item["filepath"].exists():
                    item["filepath"].unlink()
            except Exception:
                log.warning("upload_paper_files: could not clean up %s", item["filepath"])

        # Clean up temp files
        for temp_file in temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception as _e:
                log.warning("upload_paper_files: could not clean up temp %s: %s", temp_file, _e)

        log.exception("upload_paper_files failed (rolled back)", extra={"paper_id": paper_id})
        return jsonify({"error": "Upload failed", "hint": "Internal server error — the file may still be processed on our end"}), 500


@files.route("/<paper_id>/files/<int:file_id>", methods=["DELETE"])
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

    uploads = upload_folder(user_id=user_id)
    filepath = uploads / entry.file_path
    try:
        resolved = filepath.resolve()
        uploads_resolved = uploads.resolve()
        if not str(resolved).startswith(str(uploads_resolved)):
            # Fallback to legacy uploads path
            legacy_uploads = upload_folder().resolve()
            legacy_filepath = legacy_uploads / entry.file_path
            if legacy_filepath.exists() and legacy_filepath.is_file():
                legacy_filepath.unlink()
        elif filepath.exists() and filepath.is_file():
            filepath.unlink()
    except Exception:
        log.warning("delete_paper_file: could not unlink %s", filepath)
    db.session.delete(entry)
    safe_commit()
    return jsonify({"success": True})


@files.route("/<paper_id>/files/<int:file_id>/raw", methods=["GET"])
def serve_paper_file(paper_id: str, file_id: int):
    """Serve extracted text as plain text. Raw binaries are no longer stored.
    Auth: Bearer/cookie, ?s=signed, or legacy ?t=jwt."""
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

    # Raw binary not stored — serve extracted text
    if not entry.extracted_text:
        return jsonify({"error": "No extracted text available"}), 404

    from flask import make_response
    response = make_response(entry.extracted_text)
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    # Use inline disposition so browser can display it; frontend adds download attr where needed
    safe_name = Path(entry.original_name).stem.replace('"', '').replace('\r', '').replace('\n', '')
    response.headers["Content-Disposition"] = f'inline; filename="{safe_name}.txt"'
    return response


@files.route("/<paper_id>/files/<int:file_id>/preview", methods=["GET"])
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
