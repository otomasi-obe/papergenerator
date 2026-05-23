"""
Paper CRUD blueprint — list / create / read / update / delete.
Extracted from app.py to keep route concerns isolated.
"""
from __future__ import annotations

import copy
import logging
import shutil
import uuid
from datetime import datetime, timezone

import jsonpatch
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from database.models import (
    AiJob,
    ChatMessage,
    Conversation,
    ImageGenJob,
    LiteratureItem,
    Paper,
    PaperFile,
    PaperImage,
    ProjectMemory,
    SlrJob,
    db,
)
from paper_utils import PAPER_ID_RE, safe_paper_dir

log = logging.getLogger(__name__)

papers_bp = Blueprint("papers", __name__, url_prefix="/api/papers")


@papers_bp.route("", methods=["GET"])
@jwt_required()
def list_papers():
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    try:
        limit = max(1, min(int(request.args.get("limit", 20)), 100))
    except (TypeError, ValueError):
        limit = 20
    try:
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0

    q = Paper.query.filter_by(user_id=user_id).order_by(Paper.updated_at.desc())
    total = q.count()
    papers = q.limit(limit).offset(offset).all()
    return jsonify({
        "papers": [p.to_dict() for p in papers],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + len(papers) < total,
        },
    })


@papers_bp.route("", methods=["POST"])
@jwt_required()
def save_paper():
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No data provided"}), 400

    paper_id = data.get("id") or uuid.uuid4().hex[:12]
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    title = data.get("title") or (data.get("data") or {}).get("title") or "Untitled"

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if paper:
        paper.title = title
        paper.data = data
        paper.updated_at = datetime.now(timezone.utc)
    else:
        paper = Paper(id=paper_id, user_id=user_id, title=title, data=data)
        db.session.add(paper)

    db.session.commit()
    return jsonify({"success": True, "id": paper_id, "paper": paper.to_dict()})


@papers_bp.route("/<paper_id>", methods=["GET"])
@jwt_required()
def load_paper(paper_id: str):
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404
    return jsonify({**(paper.data or {}), "id": paper.id})


@papers_bp.route("/<paper_id>", methods=["PUT"])
@jwt_required()
def update_paper(paper_id: str):
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
    title = data.get("title") or (data.get("data") or {}).get("title") or "Untitled"
    paper.title = title
    paper.data = data
    paper.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"success": True, "paper": paper.to_dict()})


@papers_bp.route("/<paper_id>", methods=["DELETE"])
@jwt_required()
def delete_paper(paper_id: str):
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404

    try:
        # FKs aren't ON DELETE CASCADE at DB level — clean up dependents in the right order.
        conv_ids = [c.id for c in Conversation.query.filter_by(paper_id=paper_id).all()]
        if conv_ids:
            ChatMessage.query.filter(ChatMessage.conversation_id.in_(conv_ids)) \
                .delete(synchronize_session=False)
        Conversation.query.filter_by(paper_id=paper_id).delete(synchronize_session=False)
        ProjectMemory.query.filter_by(paper_id=paper_id).delete(synchronize_session=False)
        PaperFile.query.filter_by(paper_id=paper_id).delete(synchronize_session=False)
        PaperImage.query.filter_by(paper_id=paper_id).delete(synchronize_session=False)
        AiJob.query.filter_by(paper_id=paper_id).delete(synchronize_session=False)
        # SlrJob has a column literally named `query` which shadows the
        # Flask-SQLAlchemy `Model.query` attribute, so we must reach for
        # the session-level API here.
        db.session.query(SlrJob).filter_by(paper_id=paper_id).delete(synchronize_session=False)
        LiteratureItem.query.filter_by(paper_id=paper_id).delete(synchronize_session=False)
        ImageGenJob.query.filter_by(paper_id=paper_id).delete(synchronize_session=False)

        paper_img_dir = safe_paper_dir(paper_id)
        if paper_img_dir and paper_img_dir.exists():
            shutil.rmtree(str(paper_img_dir))

        db.session.delete(paper)
        db.session.commit()
        return jsonify({"success": True})
    except Exception:
        db.session.rollback()
        log.exception("delete_paper failed (rolled back)", extra={"paper_id": paper_id})
        return jsonify({"error": "Delete failed"}), 500


# ─── Granular edit (RFC 6902 JSON Patch) ────────────────────────────────────
# rofiq.txt #7: setelah AI generate, user mau edit bagian tertentu dengan
# presisi. Endpoint ini menerima array operasi JSON Patch, validate skema dasar,
# apply ke papers.data, lalu return paper yang baru.

PAPER_TOP_KEYS = {
    "title", "abstract", "keywords", "authors", "sections",
    "references", "figures", "tables", "equations", "acknowledgment",
}

ALLOWED_OPS = {"add", "remove", "replace", "move", "copy", "test"}


def _validate_patch_ops(ops):
    if not isinstance(ops, list) or not ops:
        return "patch must be a non-empty array of operations"
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            return f"op[{i}] must be an object"
        if op.get("op") not in ALLOWED_OPS:
            return f"op[{i}].op invalid: {op.get('op')!r}"
        path = op.get("path", "")
        if not isinstance(path, str) or not path.startswith("/"):
            return f"op[{i}].path must be a JSON pointer like /sections/0/content"
        # Hard guard: top-level path segment must be a known paper field.
        head = path.split("/", 2)[1] if "/" in path[1:] else path[1:]
        if head and head not in PAPER_TOP_KEYS:
            return f"op[{i}].path targets unknown field {head!r}"
    return None


@papers_bp.route("/<paper_id>", methods=["PATCH"])
@jwt_required()
def patch_paper(paper_id: str):
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404

    body = request.get_json(silent=True) or {}
    ops = body.get("patch") if isinstance(body, dict) else body
    err = _validate_patch_ops(ops)
    if err:
        return jsonify({"error": err}), 400

    # Apply on a deep copy so we never half-mutate live state.
    base = copy.deepcopy(paper.data or {})
    try:
        patched = jsonpatch.apply_patch(base, ops, in_place=False)
    except jsonpatch.JsonPatchException as e:
        return jsonify({"error": f"patch failed: {e}"}), 422
    except Exception as e:
        return jsonify({"error": f"patch error: {e}"}), 422

    # Optional: validate post-patch shape stays sane.
    if not isinstance(patched, dict):
        return jsonify({"error": "patch produced non-object root"}), 422

    paper.data = patched
    new_title = (
        patched.get("title")
        or (patched.get("data") or {}).get("title")
        or paper.title
        or "Untitled"
    )
    paper.title = new_title
    paper.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        "success": True,
        "applied": len(ops),
        "paper": paper.to_dict(include_data=True),
    })
