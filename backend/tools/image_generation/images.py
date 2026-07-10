"""
Paper-images blueprint — upload / list / delete + signed URL minting +
public(-ish) image serving.

Image serving accepts (priority order):
    1. Bearer header / cookie JWT (cookies travel automatically)
    2. ?s=<signed-token> for <img src> use cases
    3. ?t=<jwt> legacy fallback (kept for older clients)
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
    verify_jwt_in_request,
)

from utils.database.models import Paper, PaperImage, db, safe_commit
from tools.editor.utils import (
    FILENAME_RE,
    PAPER_ID_RE,
    is_image_bytes,
    safe_paper_image_dir,
    safe_paper_dir,
    sign_resource_token,
    verify_resource_token,
)

log = logging.getLogger(__name__)

# Two blueprints share this module: one mounted under /api/papers (CRUD on
# images for a given paper, plus the sign endpoint), another under /api/images
# for the actual byte-serving route.
paper_images = Blueprint("paper_images", __name__, url_prefix="/api/papers")
image_serve = Blueprint("image_serve", __name__, url_prefix="/api/images")

ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


@paper_images.route("/<paper_id>/images", methods=["POST"])
@jwt_required()
def upload_paper_image(paper_id: str):
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        return jsonify({"error": "Invalid image format"}), 400

    # BUG FIX #1: Add size check (was missing in original)
    file.stream.seek(0, 2)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > 10 * 1024 * 1024:
        return jsonify({"error": "Ukuran file > 10 MB"}), 413

    head = file.stream.read(16)
    file.stream.seek(0)
    if not is_image_bytes(head, ext):
        return jsonify({"error": "Invalid image file"}), 400

    paper_dir = safe_paper_image_dir(paper_id)
    if not paper_dir:
        return jsonify({"error": "Invalid paper id"}), 400
    paper_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = paper_dir / filename
    file.save(str(filepath))

    # Mirror to user storage
    try:
        from utils.core.user_storage import get_username, save_image, update_judul_paper
        _username = get_username(user_id=user_id)
        _judul = paper.title if paper else "untitled"
        save_image(_username, _judul, str(filepath))
        update_judul_paper(_username, _judul)
    except Exception:
        log.warning("upload_paper_image: gagal mirror ke user storage", exc_info=True)

    # BUG FIX #2: Add cleanup on DB failure to prevent orphaned files
    try:
        img = PaperImage(
            paper_id=paper_id,
            user_id=user_id,
            filename=filename,
            original_name=file.filename[:255],
            file_path=f"{paper_id}/{filename}",
        )
        db.session.add(img)
        safe_commit()
        return jsonify({"success": True, "image": img.to_dict()})
    except Exception:
        # Clean up orphaned file if DB commit fails
        try:
            if filepath.exists():
                filepath.unlink()
        except Exception:
            log.warning("upload_paper_image: could not clean up %s", filepath)
        db.session.rollback()
        raise


@paper_images.route("/<paper_id>/images/upload", methods=["POST"])
@jwt_required()
def upload_user_image(paper_id: str):
    """User-uploaded image variant.

    Same on-disk storage as the regular upload endpoint
    (backend/data/uploads/<paper_id>/) so the existing /api/images/<paper_id>/<file>
    serving route works unchanged. The response shape includes ``kind:
    'uploaded'`` so the chat / editor frontend can distinguish AI-generated
    images from user uploads and ask for a caption.

    Constraints:
      * multipart/form-data, field name ``file``
      * accepted MIME / extensions: png, jpeg/jpg, webp
      * size <= 10 MB (also bounded by app.config['MAX_CONTENT_LENGTH'])
    """
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    allowed = {".png", ".jpg", ".jpeg", ".webp"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed:
        return jsonify({"error": "Format harus png/jpeg/webp"}), 400

    # 10 MB cap — also enforced globally by MAX_CONTENT_LENGTH but we
    # double-check so the error message is friendly.
    file.stream.seek(0, 2)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > 10 * 1024 * 1024:
        return jsonify({"error": "Ukuran file > 10 MB"}), 413

    head = file.stream.read(16)
    file.stream.seek(0)
    if not is_image_bytes(head, ext):
        return jsonify({"error": "Invalid image file"}), 400

    paper_dir = safe_paper_image_dir(paper_id)
    if not paper_dir:
        return jsonify({"error": "Invalid paper id"}), 400
    paper_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = paper_dir / filename
    file.save(str(filepath))

    # Mirror to user storage
    try:
        from utils.core.user_storage import get_username, save_image, update_judul_paper
        _username = get_username(user_id=user_id)
        _judul = paper.title if paper else "untitled"
        save_image(_username, _judul, str(filepath))
        update_judul_paper(_username, _judul)
    except Exception:
        log.warning("upload_user_image: gagal mirror ke user storage", exc_info=True)

    # BUG FIX: Add cleanup on DB failure to prevent orphaned files
    try:
        img = PaperImage(
            paper_id=paper_id,
            user_id=user_id,
            filename=filename,
            original_name=file.filename[:255],
            file_path=f"{paper_id}/{filename}",
        )
        db.session.add(img)
        safe_commit()

        d = img.to_dict()
        return jsonify(
            {
                "id": d["id"],
                "filename": d["filename"],
                "original_name": d["original_name"],
                "url": d["url"],
                "kind": "uploaded",
                "paper_id": paper_id,
            }
        )
    except Exception:
        # Clean up orphaned file if DB commit fails
        try:
            if filepath.exists():
                filepath.unlink()
        except Exception:
            log.warning("upload_user_image: could not clean up %s", filepath)
        db.session.rollback()
        raise


@paper_images.route("/<paper_id>/images", methods=["GET"])
@jwt_required()
def list_paper_images(paper_id: str):
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404
    images = PaperImage.query.filter_by(paper_id=paper_id).order_by(PaperImage.created_at).all()
    return jsonify({"images": [img.to_dict() for img in images]})


@paper_images.route("/<paper_id>/images/<int:image_id>", methods=["DELETE"])
@jwt_required()
def delete_paper_image(paper_id: str, image_id: int):
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401
    img = PaperImage.query.filter_by(id=image_id, paper_id=paper_id, user_id=user_id).first()
    if not img:
        return jsonify({"error": "Image not found"}), 404
    paper_dir = safe_paper_image_dir(paper_id)
    if not paper_dir:
        return jsonify({"error": "Invalid paper id"}), 400
    filepath = (paper_dir / img.filename).resolve()
    try:
        filepath.relative_to(paper_dir)
        if filepath.is_file():
            filepath.unlink()
    except ValueError:
        return jsonify({'error': 'invalid path'}), 400
    except Exception:
        log.warning("delete_paper_image: could not unlink %s", filepath)
    db.session.delete(img)
    safe_commit()
    return jsonify({"success": True})


@paper_images.route("/<paper_id>/sign", methods=["POST"])
@jwt_required()
def sign_paper_resource(paper_id: str):
    """Mint a short-lived HMAC token for an image or file in this paper.
    Body: { scope: 'image' | 'file', resource_id, ttl_seconds (optional, max 3600) }
    """
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404

    data = request.get_json(silent=True) or {}
    scope = data.get("scope")
    resource_id = data.get("resource_id")
    try:
        ttl = min(max(int(data.get("ttl_seconds", 600) or 600), 60), 3600)
    except (TypeError, ValueError):
        ttl = 600
    if scope not in ("image", "file") or not resource_id:
        return (
            jsonify({"error": "scope must be 'image' or 'file' and resource_id is required"}),
            400,
        )

    rid = str(resource_id)
    token = sign_resource_token(f"{scope}:{paper_id}", rid, user_id, ttl)
    if scope == "image":
        url = f"/api/images/{paper_id}/{rid}?s={token}"
    else:
        url = f"/api/papers/{paper_id}/files/{rid}/raw?s={token}"
    return jsonify({"url": url, "expires_in": ttl})


@image_serve.route("/<paper_id>/<filename>", methods=["GET"])
def get_paper_image(paper_id: str, filename: str):
    """Serve a paper image. Cookie/Bearer JWT preferred; signed token for img tags."""
    # Sanitize filename: replace spaces and other unsafe chars (backward compat
    # with old files saved before worker sanitization was added).
    sanitized = re.sub(r'[^A-Za-z0-9_.-]', '_', filename)
    if not FILENAME_RE.match(sanitized):
        return jsonify({"error": "Invalid filename"}), 400
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400

    signed = request.args.get("s")
    if signed:
        uid = verify_resource_token(signed, f"image:{paper_id}", filename)
        if not uid:
            return jsonify({"error": "Unauthorized"}), 401
        user_id = uid
    else:
        user_id = None
        # Try query-string JWT first
        token_qs = request.args.get("t")
        if token_qs and "Authorization" not in request.headers:
            try:
                from flask_jwt_extended import decode_token
                decoded = decode_token(token_qs)
                user_id = int(decoded.get("sub"))
            except Exception:
                pass
        # Fallback: read JWT from httpOnly cookie (EventSource sends it automatically)
        if user_id is None:
            cookie_token = request.cookies.get('access_token_cookie')
            if cookie_token:
                try:
                    from flask_jwt_extended import decode_token
                    decoded = decode_token(cookie_token)
                    user_id = int(decoded.get("sub"))
                except Exception:
                    pass
        if user_id is None:
            try:
                verify_jwt_in_request()
            except Exception:
                return jsonify({"error": "Unauthorized"}), 401
            try:
                user_id = int(get_jwt_identity())
            except (ValueError, TypeError):
                return jsonify({"error": "Invalid user identity"}), 401

    # Verify paper ownership (user must own this paper to access its images)
    from utils.database.models import Paper
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()

    # Try PaperImage record first (preferred — has metadata + permissions)
    img = PaperImage.query.filter_by(paper_id=paper_id, filename=sanitized).first()
    if not img and sanitized != filename:
        img = PaperImage.query.filter_by(paper_id=paper_id, filename=filename).first()
    # If no PaperImage record, still allow serving if file exists on disk
    # (handles AI-generated images before reconcile / images saved without DB record)

    paper_dir = safe_paper_image_dir(paper_id)
    if not paper_dir:
        return jsonify({"error": "Invalid path"}), 400

    # Try sanitized filename on disk first, fall back to original
    filepath = (paper_dir / sanitized).resolve()
    if not filepath.is_file() and sanitized != filename:
        filepath = (paper_dir / filename).resolve()
    try:
        filepath.relative_to(paper_dir)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not filepath.is_file():
        stem = sanitized.rsplit(".", 1)[0]
        for alt in sorted(paper_dir.iterdir()):
            if alt.is_file() and alt.stem == stem:
                filepath = alt
                break
        else:
            return jsonify({"error": "Image not found"}), 404

    # If PaperImage record exists, verify user ownership via the record
    if img and img.user_id != user_id:
        return jsonify({"error": "Unauthorized"}), 403

    return send_file(str(filepath))
