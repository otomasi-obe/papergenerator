"""
User State API — generic key-value persistence per user, per paper.
====================================================================
Replaces scattered localStorage with server-side DB storage so that:
  - State survives refresh, tab close, device switch
  - State is isolated per user (JWT auth)
  - State is scoped per paper (optional paper_id)

Endpoints:
  GET    /api/me/state                  — load all state for current user
  GET    /api/me/state?paper_id=X       — load state for specific paper
  PUT    /api/me/state                  — batch upsert state (JSON body)
  DELETE /api/me/state/<key>            — delete single state key
  DELETE /api/me/state?paper_id=X       — delete all state for a paper
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from database.models import Paper, UserState, db, safe_commit

state_bp = Blueprint("user_state", __name__, url_prefix="/api/me/state")


@state_bp.route("", methods=["GET"])
@jwt_required()
def get_all_state():
    """Load all state for current user. Optionally filter by paper_id."""
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({'error': 'invalid identity'}), 400
    paper_id = request.args.get("paper_id")

    q = UserState.query.filter_by(user_id=user_id)
    if paper_id is not None:
        q = q.filter_by(paper_id=paper_id)

    states = q.all()
    # Return as flat dict: {key: value, ...}
    result = {}
    for s in states:
        result[s.state_key] = s.state_value

    return jsonify({"state": result, "count": len(result)}), 200


@state_bp.route("", methods=["PUT"])
@jwt_required()
def batch_upsert_state():
    """Batch upsert multiple state keys at once.

    Body: {
        "items": [
            {"key": "chat.input_text", "paper_id": "abc123", "value": "hello"},
            {"key": "ui.right_panel", "value": "chat"},
            ...
        ]
    }

    Returns: {"saved": N}
    """
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({'error': 'invalid identity'}), 400
    body = request.get_json(silent=True) or {}
    items = body.get("items", [])

    if not items:
        return jsonify({"error": "No items provided"}), 400

    saved = 0
    skipped = 0

    # Pre-validate paper_ids in ONE query. The user_states.paper_id FK to
    # papers(id) means inserting a row for a deleted/non-existent paper raises
    # ForeignKeyViolation — and because the upsert's .first() lookup triggers an
    # autoflush of rows queued earlier in the loop, a single bad paper_id used
    # to 500 the ENTIRE batch. Validate up front and skip orphan items instead.
    candidate_pids = {
        item.get("paper_id")
        for item in items
        if item.get("paper_id")
    }
    valid_pids: set[str] = set()
    if candidate_pids:
        rows = (
            db.session.query(Paper.id)
            .filter(Paper.user_id == user_id, Paper.id.in_(candidate_pids))
            .all()
        )
        valid_pids = {r[0] for r in rows}

    for item in items:
        key = item.get("key")
        value = item.get("value")
        paper_id = item.get("paper_id")

        if not key:
            continue

        # Skip state scoped to a paper that no longer exists / isn't the user's.
        if paper_id and paper_id not in valid_pids:
            skipped += 1
            continue

        # Upsert: find existing or create new
        existing = UserState.query.filter_by(
            user_id=user_id, paper_id=paper_id, state_key=key
        ).first()

        if existing:
            existing.state_value = value
        else:
            new_state = UserState(
                user_id=user_id,
                paper_id=paper_id,
                state_key=key,
                state_value=value,
            )
            db.session.add(new_state)
        saved += 1

    try:
        safe_commit()
    except Exception:
        db.session.rollback()
        raise
    return jsonify({"saved": saved, "skipped": skipped}), 200


@state_bp.route("/<key>", methods=["DELETE"])
@jwt_required()
def delete_state_key(key: str):
    """Delete a single state key."""
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({'error': 'invalid identity'}), 400
    paper_id = request.args.get("paper_id")

    q = UserState.query.filter_by(user_id=user_id, state_key=key)
    if paper_id is not None:
        q = q.filter_by(paper_id=paper_id)

    deleted = q.delete()
    try:
        safe_commit()
    except Exception:
        db.session.rollback()
        raise
    return jsonify({"deleted": deleted}), 200


@state_bp.route("", methods=["DELETE"])
@jwt_required()
def delete_all_state_for_paper():
    """Delete all state for a specific paper."""
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({'error': 'invalid identity'}), 400
    paper_id = request.args.get("paper_id")

    if not paper_id:
        return jsonify({"error": "paper_id required"}), 400

    deleted = UserState.query.filter_by(user_id=user_id, paper_id=paper_id).delete()
    try:
        safe_commit()
    except Exception:
        db.session.rollback()
        raise
    return jsonify({"deleted": deleted}), 200
