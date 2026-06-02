"""
Unit tests for quota_bp — GET /api/me/quota and quota_exceeded helper.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-real-and-not-short")
os.environ.setdefault("SECRET_KEY", "test-secret-not-real-and-not-default")
os.environ.setdefault("FLASK_ENV", "testing")

try:
    from flask import Flask
    from flask_jwt_extended import JWTManager, create_access_token

    from api.quota_bp import quota_bp, quota_exceeded
    from database.models import ApiUsageLog, User, db
except Exception as e:
    pytest.skip(f"Quota blueprint bootstrap failed: {e}", allow_module_level=True)


@pytest.fixture()
def app(tmp_path):
    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY=os.environ["JWT_SECRET_KEY"],
        JWT_COOKIE_CSRF_PROTECT=False,
        JWT_TOKEN_LOCATION=["headers"],
    )
    JWTManager(flask_app)
    db.init_app(flask_app)
    flask_app.register_blueprint(quota_bp)

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _make_user(email="alice@example.com", name="Alice", role="user", quota=1000000):
    u = User(email=email, name=name, role=role)
    u.set_password("test-password-123")
    u.token_quota_monthly = quota
    u.token_used_month = 0
    u.usage_month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    db.session.add(u)
    db.session.commit()
    return u


def _auth_headers(user):
    tok = create_access_token(identity=str(user.id))
    return {"Authorization": f"Bearer {tok}"}


def test_my_quota_success(app, client):
    with app.app_context():
        user = _make_user(quota=5000000)
        user.token_used_month = 1500000
        db.session.commit()

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        log1 = ApiUsageLog(
            user_id=user.id,
            endpoint="/api/generate",
            model="gpt-4",
            total_tokens=50000,
            prompt_tokens=10000,
            completion_tokens=40000,
            created_at=today_start + timedelta(hours=2)
        )
        log2 = ApiUsageLog(
            user_id=user.id,
            endpoint="/api/chat",
            model="gpt-3.5-turbo",
            total_tokens=30000,
            prompt_tokens=5000,
            completion_tokens=25000,
            created_at=today_start + timedelta(hours=5)
        )
        db.session.add_all([log1, log2])
        db.session.commit()

        headers = _auth_headers(user)
        resp = client.get("/api/me/quota", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()

        assert data["quota_monthly"] == 5000000
        assert data["used_month"] == 1500000
        assert data["used_today"] == 80000
        assert data["remaining"] == 3500000
        assert data["percent"] == 30.0
        assert data["is_unlimited"] is False
        assert "breakdown_by_model" in data
        assert len(data["breakdown_by_model"]) == 2


def test_my_quota_admin_unlimited(app, client):
    with app.app_context():
        admin = _make_user(email="admin@example.com", role="admin", quota=1000000)
        admin.token_used_month = 2000000
        db.session.commit()

        headers = _auth_headers(admin)
        resp = client.get("/api/me/quota", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["is_unlimited"] is True


def test_my_quota_unauthorized(client):
    resp = client.get("/api/me/quota")
    assert resp.status_code == 401


def test_my_quota_invalid_identity(app, client):
    with app.app_context():
        tok = create_access_token(identity="not-a-number")
        headers = {"Authorization": f"Bearer {tok}"}
        resp = client.get("/api/me/quota", headers=headers)

        assert resp.status_code == 401
        data = resp.get_json()
        assert "Invalid user identity" in data["error"]


def test_my_quota_user_not_found(app, client):
    with app.app_context():
        tok = create_access_token(identity="99999")
        headers = {"Authorization": f"Bearer {tok}"}
        resp = client.get("/api/me/quota", headers=headers)

        assert resp.status_code == 404
        data = resp.get_json()
        assert "User not found" in data["error"]


def test_my_quota_month_rollover(app, client):
    with app.app_context():
        user = _make_user(quota=1000000)
        user.token_used_month = 500000
        user.usage_month_key = "2026-04"
        db.session.commit()

        headers = _auth_headers(user)
        resp = client.get("/api/me/quota", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()

        assert data["used_month"] == 0

        db.session.refresh(user)
        assert user.token_used_month == 0
        assert user.usage_month_key == datetime.now(timezone.utc).strftime("%Y-%m")


def test_my_quota_no_usage_logs(app, client):
    with app.app_context():
        user = _make_user(quota=1000000)

        headers = _auth_headers(user)
        resp = client.get("/api/me/quota", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()

        assert data["used_today"] == 0
        assert data["breakdown_by_model"] == []


def test_quota_exceeded_helper_not_exceeded(app):
    with app.app_context():
        user = _make_user(quota=1000000)
        user.token_used_month = 500000
        db.session.commit()

        exceeded, error_data = quota_exceeded(user.id)

        assert exceeded is False
        assert error_data == {}


def test_quota_exceeded_helper_exceeded(app):
    with app.app_context():
        user = _make_user(quota=1000000)
        user.token_used_month = 1000000
        db.session.commit()

        exceeded, error_data = quota_exceeded(user.id)

        assert exceeded is True
        assert "monthly token quota exceeded" in error_data["error"]
        assert error_data["quota"] == 1000000
        assert error_data["used"] == 1000000
        assert "reset_at" in error_data


def test_quota_exceeded_helper_admin_bypass(app):
    with app.app_context():
        admin = _make_user(email="admin@example.com", role="admin", quota=1000000)
        admin.token_used_month = 5000000
        db.session.commit()

        exceeded, error_data = quota_exceeded(admin.id)

        assert exceeded is False
        assert error_data == {}


def test_quota_exceeded_helper_user_not_found(app):
    with app.app_context():
        exceeded, error_data = quota_exceeded(99999)

        assert exceeded is True
        assert "user not found" in error_data["error"]


def test_quota_exceeded_helper_zero_quota(app):
    with app.app_context():
        user = _make_user(quota=0)
        user.token_used_month = 100
        db.session.commit()

        exceeded, error_data = quota_exceeded(user.id)

        assert exceeded is False
        assert error_data == {}
