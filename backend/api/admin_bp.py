"""
Admin Routes Blueprint
=======================
API endpoints for admin dashboard: usage stats, all users, all papers.
"""

import logging
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required
from sqlalchemy import desc, func

from database.models import ApiUsageLog, Paper, PaperImage, User, db

log = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _require_admin():
    """Return True if current JWT user is admin."""
    claims = get_jwt()
    return claims.get("role") == "admin"


@admin_bp.route("/users", methods=["GET"])
@jwt_required()
def list_users():
    """List all registered users with pagination."""
    if not _require_admin():
        return jsonify({"error": "Admin access required"}), 403

    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    q = User.query.order_by(desc(User.created_at))
    total = q.count()
    users = q.limit(limit).offset(offset).all()

    return jsonify({
        "users": [{**u.to_dict(), "paper_count": len(u.papers)} for u in users],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + len(users) < total,
        }
    })


@admin_bp.route("/users/<int:user_id>/promote", methods=["POST"])
@jwt_required()
def promote_user(user_id):
    """Promote or demote a user's role."""
    if not _require_admin():
        return jsonify({"error": "Admin access required"}), 403

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json() or {}
    role = data.get("role", "admin")
    if role not in ("user", "admin"):
        return jsonify({"error": "Invalid role"}), 400

    user.role = role
    db.session.commit()
    return jsonify({"success": True, "message": f"{user.email} role set to {role}"})


@admin_bp.route("/users/<int:user_id>/quota", methods=["PATCH"])
@jwt_required()
def set_user_quota(user_id):
    """Admin sets monthly token quota for a user (rofiq.txt: admin set max per user)."""
    if not _require_admin():
        return jsonify({"error": "Admin access required"}), 403

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json() or {}
    try:
        quota = int(data.get("token_quota_monthly", 1000000))
    except (TypeError, ValueError):
        return jsonify({"error": "token_quota_monthly must be integer"}), 400
    if quota < 0 or quota > 10_000_000:
        return jsonify({"error": "quota out of range (0..10M)"}), 400

    user.token_quota_monthly = quota
    db.session.commit()
    return jsonify({"success": True, "user": user.to_dict()})


@admin_bp.route("/users/<int:user_id>/reset-quota", methods=["POST"])
@jwt_required()
def reset_user_quota(user_id):
    """Reset a user's monthly counter to 0 (manual reset, e.g. after billing event)."""
    if not _require_admin():
        return jsonify({"error": "Admin access required"}), 403
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    user.token_used_month = 0
    user.usage_month_key = datetime.utcnow().strftime("%Y-%m")
    db.session.commit()
    return jsonify({"success": True, "user": user.to_dict()})


@admin_bp.route("/papers", methods=["GET"])
@jwt_required()
def list_all_papers():
    """List all papers across all users with pagination."""
    if not _require_admin():
        return jsonify({"error": "Admin access required"}), 403

    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    q = Paper.query.join(User).order_by(desc(Paper.updated_at))
    total = q.count()
    papers = q.limit(limit).offset(offset).all()

    return jsonify({
        "papers": [
            {
                **p.to_dict(),
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


@admin_bp.route("/usage", methods=["GET"])
@jwt_required()
def get_usage_stats():
    """Return API token usage statistics."""
    if not _require_admin():
        return jsonify({"error": "Admin access required"}), 403

    # Aggregated totals
    total = db.session.query(
        func.sum(ApiUsageLog.total_tokens).label("total_tokens"),
        func.sum(ApiUsageLog.prompt_tokens).label("prompt_tokens"),
        func.sum(ApiUsageLog.completion_tokens).label("completion_tokens"),
        func.count(ApiUsageLog.id).label("total_calls"),
    ).first()

    # By endpoint
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

    # Daily — last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
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

    # Per user
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


@admin_bp.route("/stats", methods=["GET"])
@jwt_required()
def get_summary_stats():
    """Return summary counts for the admin overview."""
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
