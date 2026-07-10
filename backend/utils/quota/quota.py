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

from utils.database.models import ApiUsageLog, User, db, safe_commit

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

    # Calculate purchased tokens from payments
    from utils.database.models import Payment
    total_purchased = int(db.session.query(func.coalesce(func.sum(Payment.tokens), 0))
        .filter(Payment.user_id == user_id, Payment.status == 'paid').scalar() or 0)

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
            "total_purchased": total_purchased,
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


@quota.route("/token-history", methods=["GET"])
@jwt_required()
def token_history():
    """Riwayat pembelian + pengeluaran token user."""
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    from utils.database.models import Payment, ApiUsageLog, User

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # ── Pembelian token (payments) ──
    payments = (
        db.session.query(Payment)
        .filter(Payment.user_id == user_id)
        .order_by(Payment.created_at.desc())
        .limit(50)
        .all()
    )
    purchase_history = [
        {
            "id": p.id,
            "date": p.created_at.isoformat() if p.created_at else None,
            "amount": p.amount,
            "tokens": p.tokens,
            "provider": p.provider,
            "payment_method": p.payment_method,
            "status": p.status,
            "external_id": p.external_id,
        }
        for p in payments
    ]

    # ── Pengeluaran token (daily aggregation, 30 hari terakhir, bukan bulan ini) ──
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    since_30d = (now - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
    from sqlalchemy import func

    daily_usage = (
        db.session.query(
            func.date(ApiUsageLog.created_at).label("date"),
            func.coalesce(func.sum(ApiUsageLog.total_tokens), 0).label("tokens"),
            func.count(ApiUsageLog.id).label("calls"),
        )
        .filter(ApiUsageLog.user_id == user_id, ApiUsageLog.created_at >= since_30d)
        .group_by(func.date(ApiUsageLog.created_at))
        .order_by(func.date(ApiUsageLog.created_at).desc())
        .all()
    )
    usage_history = [
        {
            "date": str(r.date) if r.date else None,
            "tokens": int(r.tokens),
            "calls": int(r.calls),
        }
        for r in daily_usage
    ]

    # ── Trend: hari ini vs kemarin ──
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    today_usage = (
        db.session.query(func.coalesce(func.sum(ApiUsageLog.total_tokens), 0))
        .filter(ApiUsageLog.user_id == user_id, ApiUsageLog.created_at >= today)
        .scalar()
    ) or 0
    yest_usage = (
        db.session.query(func.coalesce(func.sum(ApiUsageLog.total_tokens), 0))
        .filter(
            ApiUsageLog.user_id == user_id,
            ApiUsageLog.created_at >= yesterday,
            ApiUsageLog.created_at < today,
        )
        .scalar()
    ) or 0
    if today_usage > yest_usage:
        trend = "up"
    elif today_usage < yest_usage:
        trend = "down"
    else:
        trend = "stable"

    # ── Total spent all-time ──
    total_spent = (
        db.session.query(func.coalesce(func.sum(ApiUsageLog.total_tokens), 0))
        .filter(ApiUsageLog.user_id == user_id)
        .scalar()
    ) or 0

    # ── Total spent this month (for BUG-4: scope monthly) ──
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_spent = (
        db.session.query(func.coalesce(func.sum(ApiUsageLog.total_tokens), 0))
        .filter(ApiUsageLog.user_id == user_id, ApiUsageLog.created_at >= month_start)
        .scalar()
    ) or 0

    # ── Total purchased ──
    total_purchased = (
        db.session.query(func.coalesce(func.sum(Payment.tokens), 0))
        .filter(Payment.user_id == user_id, Payment.status == "paid")
        .scalar()
    ) or 0

    # ── Remaining ──
    base_quota = int(user.token_quota_monthly or 0)
    used = int(user.token_used_month or 0)
    remaining = base_quota - used
    # Purchased tokens dari Payment table (paid only). base_quota di response =
    # admin-assigned portion (total quota − purchased). No heuristic guessing.
    bonus_tokens = int(total_purchased or 0)
    admin_base = max(0, base_quota - bonus_tokens)

    return jsonify({
        "purchase_history": purchase_history,
        "usage_history": usage_history,
        "trend": trend,
        "today_usage": int(today_usage),
        "yesterday_usage": int(yest_usage),
        "total_spent": int(total_spent),
        "total_spent_month": int(month_spent),
        "total_purchased": int(total_purchased),
        "remaining": remaining,
        "base_quota": admin_base,
        "bonus_tokens": bonus_tokens,
    })
