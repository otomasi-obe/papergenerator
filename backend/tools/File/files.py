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

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
    verify_jwt_in_request,
)

from utils.core import s3_storage
from database.models import Paper, PaperFile, db, safe_commit
from tools.editor.utils import (
    PAPER_ID_RE,
    safe_paper_dir,
    upload_folder,
    verify_resource_token,
)

log = logging.getLogger(__name__)

files = Blueprint("files", __name__, url_prefix="/api/papers")

ALLOWED_FILE_EXTS = {".pdf", ".docx", ".doc", ".txt", ".md", ".xlsx", ".xls", ".csv", ".pptx", ".ppt"}
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
        return text[:MAX_EXTRACT_CHARS] if text else ""
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
        return jsonify({"error": "Paper not found"}), 404
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
        return jsonify({"error": "Paper not found"}), 404

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files uploaded"}), 400

    # Phase 1: read bytes, validate, and persist (S3 or local disk)
    accepted: list[dict] = []
    warnings: list[str] = []
    temp_files: list[Path] = []  # Track temp files for cleanup

    # Pre-compute user storage context (used in both Phase 1 and Phase 2)
    try:
        from utils.core.user_storage import get_username as _get_username
        _ustor_username = _get_username(user_id=user_id)
        _ustor_judul = paper.title if paper else "untitled"
        _ustor_ok = True
    except Exception:
        _ustor_username = None
        _ustor_judul = None
        _ustor_ok = False

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
                extracted = text_fut.result(timeout=30)
            except Exception as e:
                log.info("extract_failed", extra={"file": item["name"], "err": str(e)})
                extracted = ""

            # Extract metadata result
            meta = {}
            if meta_fut is not None:
                try:
                    meta = meta_fut.result(timeout=15)
                except Exception as e:
                    log.info("meta_extract_failed", extra={"file": item["name"], "err": str(e)})

            # Save extracted text as .txt to user storage
            if _ustor_ok and extracted:
                try:
                    from utils.core.user_storage import save_file_as_txt
                    save_file_as_txt(_ustor_username, _ustor_judul, extracted, item["original_name"])
                except Exception as _e:
                    log.warning("upload_paper_files: save_file_as_txt failed for %s: %s", item["original_name"], _e)

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
            
            # Add to status.json so PaperfullTab can see it
            if _ustor_ok:
                try:
                    from utils.core.user_storage import add_status_file
                    txt_filename = Path(item["original_name"]).stem + ".txt"
                    add_status_file(
                        _ustor_username, 
                        paper_id, 
                        txt_filename, 
                        f"user/{_ustor_username}/{paper_id}/file/{txt_filename}",
                        metadata={"original_name": item["original_name"], "file_id": entry.id}
                    )
                except Exception:
                    pass
            # Include extracted text so the chat upload path can inline it
            # into the user's message in one round trip. The Files-tab UI
            # ignores this field — it calls /preview on demand.
            saved.append(entry.to_dict(include_text=True))

        safe_commit()

        # Delete raw binary files — only extracted text is persisted.
        # S3 uploads and local files are removed after successful extraction.
        for item in accepted:
            try:
                if s3_storage.is_s3_enabled():
                    s3_storage.delete_file(item["s3_key"])
                elif item["filepath"].exists():
                    item["filepath"].unlink()
            except Exception:
                log.warning("upload_paper_files: could not clean raw %s", item["filepath"])
        # Clean up temp files
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
            except Exception as _e:
                log.warning("upload_paper_files: could not clean up temp %s: %s", temp_file, _e)

        log.exception("upload_paper_files failed (rolled back)", extra={"paper_id": paper_id})
        return jsonify({"error": "Upload failed"}), 500


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

    filepath = upload_folder() / entry.file_path
    try:
        resolved = filepath.resolve()
        uploads = upload_folder().resolve()
        if not str(resolved).startswith(str(uploads)):
            return jsonify({'error': 'invalid path'}), 400
        if filepath.exists() and filepath.is_file():
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
