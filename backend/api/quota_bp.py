"""
User-facing quota endpoint — used by the header bar in the frontend.
GET /api/me/quota → {used, quota, percent, breakdown_by_model}
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func

from database.models import ApiUsageLog, User, db

quota_bp = Blueprint("quota", __name__, url_prefix="/api/me")


@quota_bp.route("/quota", methods=["GET"])
@jwt_required()
def my_quota():
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    now = datetime.now(timezone.utc)
    month_key = now.strftime("%Y-%m")

    # Auto-roll if month changed since last write.
    if (user.usage_month_key or "") != month_key:
        user.usage_month_key = month_key
        user.token_used_month = 0
        db.session.commit()

    # Today's usage from logs (cheap aggregate; index on user_id+created_at).
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_total = (
        db.session.query(func.coalesce(func.sum(ApiUsageLog.total_tokens), 0))
        .filter(ApiUsageLog.user_id == user_id, ApiUsageLog.created_at >= today_start)
        .scalar()
    ) or 0

    # Breakdown by model for this month.
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    by_model = (
        db.session.query(
            ApiUsageLog.model,
            func.coalesce(func.sum(ApiUsageLog.total_tokens), 0).label("tokens"),
            func.count(ApiUsageLog.id).label("calls"),
        )
        .filter(ApiUsageLog.user_id == user_id, ApiUsageLog.created_at >= month_start)
        .group_by(ApiUsageLog.model)
        .all()
    )

    quota = int(user.token_quota_monthly or 0)
    used = int(user.token_used_month or 0)
    percent = round(min(100, (used / quota * 100) if quota > 0 else 0), 1)

    return jsonify(
        {
            "quota_monthly": quota,
            "used_month": used,
            "used_today": int(today_total),
            "remaining": max(0, quota - used),
            "percent": percent,
            "month_key": month_key,
            "breakdown_by_model": [
                {"model": m or "unknown", "tokens": int(t), "calls": int(c)} for m, t, c in by_model
            ],
            "is_unlimited": user.role == "admin",
        }
    )


def quota_exceeded(user_id: int) -> tuple[bool, dict]:
    """Reusable check from generate / chat endpoints. Admins bypass."""
    user = User.query.get(int(user_id))
    if not user:
        return True, {"error": "user not found"}
    if user.role == "admin":
        return False, {}
    quota = int(user.token_quota_monthly or 0)
    used = int(user.token_used_month or 0)
    if quota > 0 and used >= quota:
        reset_epoch = (
            datetime.now(timezone.utc)
            .replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
            + 31 * 86400
        )
        return True, {
            "error": "monthly token quota exceeded",
            "quota": quota,
            "used": used,
            "reset_at": int(reset_epoch),
        }
    return False, {}
