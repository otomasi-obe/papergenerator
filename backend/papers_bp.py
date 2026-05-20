"""
Paper CRUD blueprint — list / create / read / update / delete.
Extracted from app.py to keep route concerns isolated.
"""
from __future__ import annotations

import logging
import shutil
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from models import (
    ChatMessage,
    Conversation,
    Paper,
    PaperFile,
    PaperImage,
    ProjectMemory,
    db,
)
from paper_utils import PAPER_ID_RE, safe_paper_dir

log = logging.getLogger(__name__)

papers_bp = Blueprint("papers", __name__, url_prefix="/api/papers")


@papers_bp.route("", methods=["GET"])
@jwt_required()
def list_papers():
    user_id = int(get_jwt_identity())
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
    user_id = int(get_jwt_identity())
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
    user_id = int(get_jwt_identity())
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404
    return jsonify({**(paper.data or {}), "id": paper.id})


@papers_bp.route("/<paper_id>", methods=["PUT"])
@jwt_required()
def update_paper(paper_id: str):
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    user_id = int(get_jwt_identity())
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
    user_id = int(get_jwt_identity())
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
