"""
Paper CRUD blueprint — list / create / read / update / delete.
Extracted from app.py to keep route concerns isolated.
"""

from __future__ import annotations

import copy
import json
import logging
import shutil
import uuid
from pathlib import Path
from datetime import datetime, timezone

import jsonpatch
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from utils.database.models import (
    AiJob,
    ChatDraft,
    ChatMessage,
    Conversation,
    ImageGenJob,
    LiteratureItem,
    Paper,
    PaperFile,
    PaperImage,
    ProjectMemory,
    SlrJob,
    UserState,
    db,
safe_commit,)
from utils.middleware import validate_query, validate_request
from tools.editor.utils import PAPER_ID_RE, safe_paper_dir
from utils.schemas import PAPER_CREATE_SCHEMA, PAPER_LIST_QUERY_SCHEMA, PAPER_UPDATE_SCHEMA
from utils.core.user_storage import get_status_json, get_username

log = logging.getLogger(__name__)

papers = Blueprint("papers", __name__, url_prefix="/api/papers")


def _extract_title(data: dict) -> str:
    """Extract a usable title from the request payload, defaulting to 'Untitled'.

    The frontend sends a flat structure (title at top level). Handles empty
    strings, None, and whitespace-only values.
    """
    title = (data.get("title") or "").strip()
    return title if title else "Untitled"


@papers.route("", methods=["GET"])
@jwt_required()
@validate_query(PAPER_LIST_QUERY_SCHEMA)
def list_papers():
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    limit = int(request.args.get("limit", 20))
    offset = int(request.args.get("offset", 0))

    # Optimize: use window function to get count without separate query

    q = Paper.query.filter_by(user_id=user_id).order_by(Paper.updated_at.desc())
    papers = q.limit(limit).offset(offset).all()

    # Get total count efficiently - only if we need it for pagination
    total = q.count()

    # Pre-load image counts in a single query to avoid N+1
    paper_ids = [p.id for p in papers]
    image_counts = {}
    if paper_ids:
        from utils.database.models import PaperImage
        rows = (
            db.session.query(PaperImage.paper_id, db.func.count(PaperImage.id))
            .filter(PaperImage.paper_id.in_(paper_ids))
            .group_by(PaperImage.paper_id)
            .all()
        )
        image_counts = dict(rows)

    return jsonify(
        {
            "papers": [p.to_dict(image_count=image_counts.get(p.id, 0)) for p in papers],
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total,
                "has_more": len(papers) == limit,  # Optimized check
            },
        }
    )


@papers.route("", methods=["POST"])
@jwt_required()
@validate_request(PAPER_CREATE_SCHEMA, required=False)
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
    title = _extract_title(data)

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if paper:
        paper.title = title
        paper.data = data
        paper.updated_at = datetime.now(timezone.utc)
    else:
        paper = Paper(id=paper_id, user_id=user_id, title=title, data=data)
        db.session.add(paper)

    try:
        safe_commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Paper with this ID already exists"}), 409
    except Exception:
        db.session.rollback()
        raise
    # Save paper.json to user storage
    try:
        from utils.core.user_storage import get_username, save_paper_json_by_id
        _username = get_username(user_id=user_id)
        save_paper_json_by_id(_username, paper_id, data)
    except Exception:
        log.exception("save_paper_json_by_id failed", extra={"paper_id": paper_id, "user_id": user_id})
    return jsonify({"success": True, "id": paper_id, "paper": paper.to_dict()})


@papers.route("/<paper_id>", methods=["GET"])
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

    data = dict(paper.data or {})

    # Reconcile section images so gambar items get actual file paths
    try:
        from tools.editor.utils import safe_paper_image_dir
        from tools.paperfull.jobs import _reconcile_section_images
        _image_dir = safe_paper_image_dir(paper_id)
        if _image_dir and _image_dir.exists():
            # _reconcile_section_images expects the paper root dir, not image subdir
            _paper_root = _image_dir.parent
            _reconcile_section_images(data, paper_id, _paper_root)
    except Exception:
        log.debug("[load_paper] image reconciliation skipped/failed", exc_info=True)

    # Clean LaTeX → Unicode in all string values for preview readability.
    # DOCX export has its own OMML pipeline; this is read-only view only.
    try:
        from tools.Journal._math_omml import clean_latex_for_preview as _clfp

        # Keys whose values are file paths / identifiers — NOT LaTeX text.
        _PATH_KEYS = frozenset({"Path", "path", "Prompt", "prompt", "id", "filename"})

        def _walk(obj, key=None):
            if isinstance(obj, str):
                # Skip file paths and identifiers
                if key in _PATH_KEYS:
                    return obj
                return _clfp(obj)
            if isinstance(obj, dict):
                return {k: _walk(v, k) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_walk(v, key) for v in obj]
            return obj

        data = _walk(data)
    except Exception:
        pass  # never break preview over a cleaner failure

    return jsonify({**data, "id": paper.id})


@papers.route("/<paper_id>", methods=["PUT"])
@jwt_required()
@validate_request(PAPER_UPDATE_SCHEMA, required=False)
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
    title = _extract_title(data)
    paper.title = title
    paper.data = data
    paper.updated_at = datetime.now(timezone.utc)
    try:
        safe_commit()
    except Exception:
        db.session.rollback()
        raise
    # Save paper.json to user storage after DB commit succeeds
    try:
        from utils.core.user_storage import get_username, save_paper_json_by_id
        _username = get_username(user_id=user_id)
        save_paper_json_by_id(_username, paper_id, data)
    except Exception:
        log.exception("save_paper_json_by_id failed on update", extra={"paper_id": paper_id, "user_id": user_id})
    return jsonify({"success": True, "paper": paper.to_dict()})


@papers.route("/<paper_id>", methods=["DELETE"])
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
            ChatMessage.query.filter(ChatMessage.conversation_id.in_(conv_ids)).delete(
                synchronize_session=False
            )
        Conversation.query.filter_by(paper_id=paper_id).delete(synchronize_session=False)
        ProjectMemory.query.filter_by(paper_id=paper_id).delete(synchronize_session=False)
        PaperFile.query.filter_by(paper_id=paper_id).delete(synchronize_session=False)
        # ImageGenJob must be deleted BEFORE PaperImage because it has FK to paper_images.id
        ImageGenJob.query.filter_by(paper_id=paper_id).delete(synchronize_session=False)
        PaperImage.query.filter_by(paper_id=paper_id).delete(synchronize_session=False)
        AiJob.query.filter_by(paper_id=paper_id).delete(synchronize_session=False)
        # SlrJob has a column literally named `query` which shadows the
        # Flask-SQLAlchemy `Model.query` attribute, so we must reach for
        # the session-level API here.
        db.session.query(SlrJob).filter_by(paper_id=paper_id).delete(synchronize_session=False)
        LiteratureItem.query.filter_by(paper_id=paper_id).delete(synchronize_session=False)
        # Use raw SQL for chat_drafts/user_states to avoid any ORM
        # column-shadowing issues (e.g. ChatDraft.name, etc.)
        from sqlalchemy import text as _sa_text
        db.session.execute(_sa_text("DELETE FROM chat_drafts WHERE paper_id = :pid"), {"pid": paper_id})
        db.session.execute(_sa_text("DELETE FROM user_states WHERE paper_id = :pid"), {"pid": paper_id})

        db.session.delete(paper)

        # Mark user storage JSON as deleted instead of removing it
        # Commit DB FIRST before touching filesystem so rollback is possible
        safe_commit()
        try:
            import json as _json
            from utils.core.user_storage import get_username, get_paper_base_by_id
            _username = get_username(user_id=user_id)
            base_dir = get_paper_base_by_id(_username, paper_id)
            deleted_json = base_dir / f"{paper_id}.json"
            if deleted_json.exists():
                with open(deleted_json, 'r') as f:
                    data = _json.load(f)
                data['deleted'] = True
                data['deleted_at'] = datetime.now(timezone.utc).isoformat()
                with open(deleted_json, 'w') as f:
                    _json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

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
    "title",
    "abstract",
    "keywords",
    "authors",
    "sections",
    "references",
    "figures",
    "tables",
    "equations",
    "acknowledgment",
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


@papers.route("/<paper_id>", methods=["PATCH"])
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
        log.warning("JSON patch failed: %s", e)
        return jsonify({"error": "patch failed"}), 422
    except Exception as e:
        log.warning("JSON patch error: %s", e)
        return jsonify({"error": "patch error"}), 422

    # Optional: validate post-patch shape stays sane.
    if not isinstance(patched, dict):
        return jsonify({"error": "patch produced non-object root"}), 422

    paper.data = patched
    new_title = (patched.get("title") or "").strip() or paper.title or "Untitled"
    paper.title = new_title
    paper.updated_at = datetime.now(timezone.utc)
    safe_commit()
    # Save paper.json to user storage after DB commit succeeds
    try:
        from utils.core.user_storage import get_username, save_paper_json_by_id
        _username = get_username(user_id=user_id)
        save_paper_json_by_id(_username, paper_id, patched)
    except Exception:
        log.exception("save_paper_json_by_id failed on patch", extra={"paper_id": paper_id, "user_id": user_id})

    return jsonify(
        {
            "success": True,
            "applied": len(ops),
            "paper": paper.to_dict(include_data=True),
        }
    )


@papers.route("/<paper_id>/status", methods=["GET"])
@jwt_required()
def get_paper_status(paper_id):
    """Get status.json untuk paper - berisi facts, files, tables yang dikumpulkan dari chat."""
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404

    try:
        username = get_username(user_id=user_id)
        status_data = get_status_json(username, paper_id)
        return jsonify(status_data)
    except Exception as e:
        log.error(f"Failed to get status for paper {paper_id}: {e}")
        return jsonify({"error": "Failed to retrieve status"}), 500


@papers.route("/template/<lang>", methods=["GET"])
@jwt_required()
def get_paper_template(lang: str):
    """Return the language-specific paper template JSON (en.json / id.json)."""
    if lang not in ("en", "id"):
        return jsonify({"error": "Unsupported language"}), 400

    prompt_dir = Path(__file__).resolve().parent.parent / "paperfull" / "prompt"
    template_path = prompt_dir / f"{lang}.json"

    if not template_path.exists():
        return jsonify({"error": "Template not found"}), 404

    try:
        data = json.loads(template_path.read_text(encoding="utf-8"))
        return jsonify(data)
    except Exception as e:
        log.error(f"Failed to read template {lang}: {e}")
        return jsonify({"error": "Failed to read template"}), 500
