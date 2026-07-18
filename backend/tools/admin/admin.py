"""
Admin Routes Blueprint
=======================
API endpoints for admin dashboard: usage stats, all users, all papers.
"""

import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import desc, func

from utils.database.models import ApiUsageLog, Paper, PaperDeleteLog, PaperImage, User, db, safe_commit

log = logging.getLogger(__name__)

admin = Blueprint("admin", __name__, url_prefix="/api/admin")


def _require_admin():
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return False
    user = User.query.get(user_id)
    return bool(user and user.role == "admin")


@admin.route("/users", methods=["GET"])
@jwt_required()
def list_users():
    if not _require_admin():
        return jsonify({"error": "Admin access required"}), 403

    try:
        limit = min(int(request.args.get("limit", 50)), 2000)
        offset = max(int(request.args.get("offset", 0)), 0)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid limit/offset parameter"}), 400

    q = User.query.order_by(desc(User.created_at))
    total = q.count()
    users = q.limit(limit).offset(offset).all()

    # Pre-load paper counts in a single query to avoid N+1
    user_ids = [u.id for u in users]
    paper_counts = {}
    if user_ids:
        rows = (
            db.session.query(Paper.user_id, func.count(Paper.id))
            .filter(Paper.user_id.in_(user_ids))
            .group_by(Paper.user_id)
            .all()
        )
        paper_counts = dict(rows)

    return jsonify({
        "users": [{**u.to_dict(), "paper_count": paper_counts.get(u.id, 0)} for u in users],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + len(users) < total,
        }
    })


@admin.route("/users/<int:user_id>/promote", methods=["POST"])
@jwt_required()
def promote_user(user_id):
    if not _require_admin():
        return jsonify({"error": "Admin access required"}), 403

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    role = data.get("role", "admin")
    if role not in ("user", "admin"):
        return jsonify({"error": "Invalid role"}), 400

    user.role = role
    safe_commit()
    return jsonify({"success": True, "message": f"{user.email} role set to {role}"})


@admin.route("/users/<int:user_id>/quota", methods=["PATCH"])
@jwt_required()
def set_user_quota(user_id):
    if not _require_admin():
        return jsonify({"error": "Admin access required"}), 403

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    try:
        quota = int(data.get("token_quota_monthly", 500000))
    except (TypeError, ValueError):
        return jsonify({"error": "token_quota_monthly must be integer"}), 400
    if quota < 0 or quota > 10_000_000:
        return jsonify({"error": "quota out of range (0..10M)"}), 400

    user.token_quota_monthly = quota
    safe_commit()
    return jsonify({"success": True, "user": user.to_dict()})


@admin.route("/users/<int:user_id>/reset-quota", methods=["POST"])
@jwt_required()
def reset_user_quota(user_id):
    if not _require_admin():
        return jsonify({"error": "Admin access required"}), 403
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    user.token_used_month = 0
    user.usage_month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    safe_commit()
    return jsonify({"success": True, "user": user.to_dict()})


@admin.route("/papers", methods=["GET"])
@jwt_required()
def list_all_papers():
    if not _require_admin():
        return jsonify({"error": "Admin access required"}), 403

    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid limit/offset parameter"}), 400

    q = Paper.query.join(User).order_by(desc(Paper.updated_at))
    total = q.count()
    papers = q.limit(limit).offset(offset).all()

    # Pre-load image counts in a single query to avoid N+1
    paper_ids = [p.id for p in papers]
    image_counts = {}
    if paper_ids:
        rows = (
            db.session.query(PaperImage.paper_id, func.count(PaperImage.id))
            .filter(PaperImage.paper_id.in_(paper_ids))
            .group_by(PaperImage.paper_id)
            .all()
        )
        image_counts = dict(rows)

    return jsonify({
        "papers": [
            {
                **p.to_dict(image_count=image_counts.get(p.id, 0)),
                "user_email": p.user.email,
                "user_name": p.user.name,
            }
            for p in papers
        ],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + len(papers) < total,
        }
    })


@admin.route("/usage", methods=["GET"])
@jwt_required()
def get_usage_stats():
    if not _require_admin():
        return jsonify({"error": "Admin access required"}), 403

    total = db.session.query(
        func.sum(ApiUsageLog.total_tokens).label("total_tokens"),
        func.sum(ApiUsageLog.prompt_tokens).label("prompt_tokens"),
        func.sum(ApiUsageLog.completion_tokens).label("completion_tokens"),
        func.count(ApiUsageLog.id).label("total_calls"),
    ).first()

    by_endpoint = (
        db.session.query(
            ApiUsageLog.endpoint,
            func.count(ApiUsageLog.id).label("calls"),
            func.sum(ApiUsageLog.total_tokens).label("tokens"),
        )
        .group_by(ApiUsageLog.endpoint)
        .order_by(desc("tokens"))
        .all()
    )

    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    daily = (
        db.session.query(
            func.date(ApiUsageLog.created_at).label("date"),
            func.count(ApiUsageLog.id).label("calls"),
            func.sum(ApiUsageLog.total_tokens).label("tokens"),
        )
        .filter(ApiUsageLog.created_at >= thirty_days_ago)
        .group_by(func.date(ApiUsageLog.created_at))
        .order_by(func.date(ApiUsageLog.created_at))
        .all()
    )

    per_user = (
        db.session.query(
            User.email,
            User.name,
            func.count(ApiUsageLog.id).label("calls"),
            func.sum(ApiUsageLog.total_tokens).label("tokens"),
        )
        .join(User, ApiUsageLog.user_id == User.id)
        .group_by(User.id, User.email, User.name)
        .order_by(desc("tokens"))
        .all()
    )

    return jsonify(
        {
            "total": {
                "calls": int(total.total_calls or 0),
                "total_tokens": int(total.total_tokens or 0),
                "prompt_tokens": int(total.prompt_tokens or 0),
                "completion_tokens": int(total.completion_tokens or 0),
            },
            "by_endpoint": [
                {"endpoint": e, "calls": int(c), "tokens": int(t or 0)} for e, c, t in by_endpoint
            ],
            "daily": [
                {"date": str(d), "calls": int(c), "tokens": int(t or 0)} for d, c, t in daily
            ],
            "per_user": [
                {"email": e, "name": n, "calls": int(c), "tokens": int(t or 0)}
                for e, n, c, t in per_user
            ],
        }
    )


@admin.route("/stats", methods=["GET"])
@jwt_required()
def get_summary_stats():
    if not _require_admin():
        return jsonify({"error": "Admin access required"}), 403

    total_users = User.query.count()
    total_papers = Paper.query.count()
    total_images = PaperImage.query.count()
    total_tokens = db.session.query(func.sum(ApiUsageLog.total_tokens)).scalar() or 0
    total_calls = ApiUsageLog.query.count()

    return jsonify(
        {
            "total_users": total_users,
            "total_papers": total_papers,
            "total_images": total_images,
            "total_tokens": int(total_tokens),
            "total_api_calls": total_calls,
        }
    )


@admin.route("/delete-log", methods=["GET"])
@jwt_required()
def get_delete_log():
    """Return recent paper deletion logs for admin dashboard."""
    if not _require_admin():
        return jsonify({"error": "Admin access required"}), 403

    try:
        limit = min(int(request.args.get("limit", 200)), 500)
        offset = int(request.args.get("offset", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid limit/offset"}), 400

    q = PaperDeleteLog.query.order_by(desc(PaperDeleteLog.deleted_at))
    total = q.count()
    logs = q.limit(limit).offset(offset).all()

    return jsonify({
        "logs": [log.to_dict() for log in logs],
        "pagination": {"limit": limit, "offset": offset, "total": total},
    })
