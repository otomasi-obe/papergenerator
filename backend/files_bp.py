"""
Paper-files blueprint — list / upload / delete / preview / serve raw.
Auth modes for /raw mirror app.py: Bearer header, signed token (?s=), or
legacy ?t=jwt. Cookies travel automatically because JWT_TOKEN_LOCATION
includes both cookies and headers.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
    verify_jwt_in_request,
)

from models import Paper, PaperFile, db
from paper_utils import (
    PAPER_ID_RE,
    safe_paper_dir,
    upload_folder,
    verify_resource_token,
)

log = logging.getLogger(__name__)

files_bp = Blueprint("paper_files", __name__, url_prefix="/api/papers")

ALLOWED_FILE_EXTS = {".pdf", ".docx", ".doc", ".txt", ".md"}
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PREVIEW_CHARS = 20_000


def _extract_text_for_preview(filepath: Path, ext: str) -> str:
    try:
        if ext == ".pdf":
            from extract_pdfs import extract_text_from_pdf
            with open(filepath, "rb") as f:
                txt = extract_text_from_pdf(f)
            return txt[:MAX_PREVIEW_CHARS]
        if ext in (".docx", ".doc"):
            from docx import Document
            doc = Document(str(filepath))
            return "\n".join(p.text for p in doc.paragraphs)[:MAX_PREVIEW_CHARS]
        if ext in (".txt", ".md"):
            return filepath.read_text(encoding="utf-8", errors="replace")[:MAX_PREVIEW_CHARS]
    except Exception:
        return ""
    return ""


@files_bp.route("/<paper_id>/files", methods=["GET"])
@jwt_required()
def list_paper_files(paper_id: str):
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    user_id = int(get_jwt_identity())
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404
    files = (
        PaperFile.query.filter_by(paper_id=paper_id)
        .order_by(PaperFile.created_at.desc())
        .all()
    )
    return jsonify({"files": [f.to_dict() for f in files]})


@files_bp.route("/<paper_id>/files", methods=["POST"])
@jwt_required()
def upload_paper_files(paper_id: str):
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    user_id = int(get_jwt_identity())
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files uploaded"}), 400

    paper_dir = safe_paper_dir(paper_id)
    if not paper_dir:
        return jsonify({"error": "Invalid paper id"}), 400
    files_dir = paper_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    saved, warnings = [], []
    try:
        for f in files:
            ext = Path(f.filename or "").suffix.lower()
            if ext not in ALLOWED_FILE_EXTS:
                warnings.append(f"{f.filename}: format tidak didukung")
                continue

            data = f.stream.read()
            if len(data) > MAX_FILE_BYTES:
                warnings.append(f"{f.filename}: lebih dari 10MB, dilewati")
                continue

            name = f"{uuid.uuid4().hex}{ext}"
            filepath = files_dir / name
            filepath.write_bytes(data)

            entry = PaperFile(
                paper_id=paper_id,
                user_id=user_id,
                filename=name,
                original_name=(f.filename or "")[:255],
                ext=ext,
                size_bytes=len(data),
                file_path=f"{paper_id}/files/{name}",
                extracted_text=_extract_text_for_preview(filepath, ext),
            )
            db.session.add(entry)
            db.session.flush()
            saved.append(entry.to_dict())

        db.session.commit()
        return jsonify({"success": True, "files": saved, "warnings": warnings})
    except Exception:
        db.session.rollback()
        log.exception("upload_paper_files failed (rolled back)",
                      extra={"paper_id": paper_id})
        return jsonify({"error": "Upload failed"}), 500


@files_bp.route("/<paper_id>/files/<int:file_id>", methods=["DELETE"])
@jwt_required()
def delete_paper_file(paper_id: str, file_id: int):
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    user_id = int(get_jwt_identity())
    entry = PaperFile.query.filter_by(
        id=file_id, paper_id=paper_id, user_id=user_id
    ).first()
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
        token_qs = request.args.get("t")
        if token_qs and "Authorization" not in request.headers:
            request.headers.environ["HTTP_AUTHORIZATION"] = f"Bearer {token_qs}"
        try:
            verify_jwt_in_request()
        except Exception:
            return jsonify({"error": "Unauthorized"}), 401
        user_id = int(get_jwt_identity())

    entry = PaperFile.query.filter_by(
        id=file_id, paper_id=paper_id, user_id=user_id
    ).first()
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
    user_id = int(get_jwt_identity())
    entry = PaperFile.query.filter_by(
        id=file_id, paper_id=paper_id, user_id=user_id
    ).first()
    if not entry:
        return jsonify({"error": "File not found"}), 404
    return jsonify({
        "id": entry.id,
        "ext": entry.ext,
        "original_name": entry.original_name,
        "text": entry.extracted_text or "",
        "raw_url": f"/api/papers/{paper_id}/files/{file_id}/raw",
    })
