"""
User-facing quota endpoint — used by the header bar in the frontend.
GET /api/me/quota → {used, quota, percent, breakdown_by_model}
"""

from __future__ import annotations

import calendar
from datetime import datetime, timezone

from flask import Blueprint, jsonify, has_app_context
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func

from database.models import ApiUsageLog, User, db, safe_commit

quota = Blueprint("quota", __name__, url_prefix="/api/me")


@quota.route("/quota", methods=["GET"])
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

    if (user.usage_month_key or "") != month_key:
        user.usage_month_key = month_key
        user.token_used_month = 0
        safe_commit()

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_total = (
        db.session.query(func.coalesce(func.sum(ApiUsageLog.total_tokens), 0))
        .filter(ApiUsageLog.user_id == user_id, ApiUsageLog.created_at >= today_start)
        .scalar()
    ) or 0

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    by_model = (
        db.session.query(
            ApiUsageLog.model,
            func.coalesce(func.sum(ApiUsageLog.total_tokens), 0).label("tokens"),
            func.count(ApiUsageLog.id).label("calls"),
            func.coalesce(func.sum(ApiUsageLog.prompt_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(ApiUsageLog.completion_tokens), 0).label("output_tokens"),
        )
        .filter(ApiUsageLog.user_id == user_id, ApiUsageLog.created_at >= month_start)
        .group_by(ApiUsageLog.model)
        .all()
    )

    quota_val = int(user.token_quota_monthly or 0)
    used = int(user.token_used_month or 0)
    percent = round(min(100, (used / quota_val * 100) if quota_val > 0 else 0), 1)

    # Calculate total input/output tokens across all models
    total_input = sum(int(r[3]) for r in by_model)
    total_output = sum(int(r[4]) for r in by_model)

    return jsonify(
        {
            "quota_monthly": quota_val,
            "used_month": used,
            "used_today": int(today_total),
            "remaining": max(0, quota_val - used),
            "percent": percent,
            "month_key": month_key,
            "input_tokens": total_input,
            "output_tokens": total_output,
            "breakdown_by_model": [
                {"model": m or "unknown", "tokens": int(t), "calls": int(c), "input_tokens": int(inp), "output_tokens": int(out)} 
                for m, t, c, inp, out in by_model
            ],
            "is_unlimited": user.role == "admin",
        }
    )


def quota_exceeded(user_id: int) -> tuple[bool, dict]:
    if not has_app_context():
        from utils.job_core import get_core_app
        _ctx = get_core_app().app_context()
        _ctx.__enter__()
    else:
        _ctx = None
    try:
        user = User.query.get(int(user_id))
        if not user:
            return True, {"error": "user not found"}
        if user.role == "admin":
            return False, {}
        quota_val = int(user.token_quota_monthly or 0)
        used = int(user.token_used_month or 0)
        if quota_val > 0 and used >= quota_val:
            # BUG-20: Use calendar.monthrange instead of hardcoded 31 days
            _now = datetime.now(timezone.utc)
            _days_in_month = calendar.monthrange(_now.year, _now.month)[1]
            reset_epoch = (
                _now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                .timestamp()
                + _days_in_month * 86400
            )
            return True, {
                "error": "monthly token quota exceeded",
                "quota": quota_val,
                "used": used,
                "reset_at": int(reset_epoch),
            }
        return False, {}
    finally:
        if _ctx:
            _ctx.__exit__(None, None, None)
