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
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
    verify_jwt_in_request,
)

from database.models import Paper, PaperImage, db
from paper_generation.utils import (
    FILENAME_RE,
    PAPER_ID_RE,
    is_image_bytes,
    safe_paper_dir,
    sign_resource_token,
    upload_folder,
    verify_resource_token,
)

log = logging.getLogger(__name__)

# Two blueprints share this module: one mounted under /api/papers (CRUD on
# images for a given paper, plus the sign endpoint), another under /api/images
# for the actual byte-serving route.
paper_images_bp = Blueprint("paper_images", __name__, url_prefix="/api/papers")
image_serve_bp = Blueprint("image_serve", __name__, url_prefix="/api/images")

ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


@paper_images_bp.route("/<paper_id>/images", methods=["POST"])
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

    paper_dir = safe_paper_dir(paper_id)
    if not paper_dir:
        return jsonify({"error": "Invalid paper id"}), 400
    paper_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = paper_dir / filename
    file.save(str(filepath))

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
        db.session.commit()
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


@paper_images_bp.route("/<paper_id>/images/upload", methods=["POST"])
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

    paper_dir = safe_paper_dir(paper_id)
    if not paper_dir:
        return jsonify({"error": "Invalid paper id"}), 400
    paper_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = paper_dir / filename
    file.save(str(filepath))

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
        db.session.commit()

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


@paper_images_bp.route("/<paper_id>/images", methods=["GET"])
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


@paper_images_bp.route("/<paper_id>/images/<int:image_id>", methods=["DELETE"])
@jwt_required()
def delete_paper_image(paper_id: str, image_id: int):
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    user_id = int(get_jwt_identity())
    img = PaperImage.query.filter_by(id=image_id, paper_id=paper_id, user_id=user_id).first()
    if not img:
        return jsonify({"error": "Image not found"}), 404
    filepath = upload_folder() / img.file_path
    try:
        if filepath.exists():
            filepath.unlink()
    except Exception:
        log.warning("delete_paper_image: could not unlink %s", filepath)
    db.session.delete(img)
    db.session.commit()
    return jsonify({"success": True})


@paper_images_bp.route("/<paper_id>/sign", methods=["POST"])
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


@image_serve_bp.route("/<paper_id>/<filename>", methods=["GET"])
def get_paper_image(paper_id: str, filename: str):
    """Serve a paper image. Cookie/Bearer JWT preferred; signed token for img tags."""
    if not FILENAME_RE.match(filename):
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
        token_qs = request.args.get("t")
        if token_qs and "Authorization" not in request.headers:
            request.headers.environ["HTTP_AUTHORIZATION"] = f"Bearer {token_qs}"
        try:
            verify_jwt_in_request()
        except Exception:
            return jsonify({"error": "Unauthorized"}), 401
        try:
            user_id = int(get_jwt_identity())
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid user identity"}), 401

    # Verify both paper ownership AND image belongs to that paper (security fix)
    img = PaperImage.query.filter_by(paper_id=paper_id, filename=filename).first()
    if not img:
        return jsonify({"error": "Image not found"}), 404
    if img.user_id != user_id:
        return jsonify({"error": "Unauthorized"}), 403

    paper_dir = safe_paper_dir(paper_id)
    if not paper_dir:
        return jsonify({"error": "Invalid path"}), 400

    filepath = (paper_dir / filename).resolve()
    try:
        filepath.relative_to(paper_dir)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not filepath.is_file():
        return jsonify({"error": "Image not found"}), 404
    return send_file(str(filepath))
