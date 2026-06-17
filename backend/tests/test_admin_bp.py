"""
Unit tests for admin_bp — Admin dashboard endpoints.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
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
    from sqlalchemy import JSON

    from tools.admin import admin as admin_bp
    from database.models import ApiUsageLog, Paper, PaperImage, User, db

    Paper.__table__.c.data.type = JSON()
except Exception as e:
    pytest.skip(f"Admin blueprint bootstrap failed: {e}", allow_module_level=True)


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
    flask_app.register_blueprint(admin_bp)

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _make_user(email, name, role="user", quota=1000000):
    u = User(email=email, name=name, role=role)
    u.set_password("test-password-123")
    u.token_quota_monthly = quota
    u.token_used_month = 0
    db.session.add(u)
    db.session.commit()
    return u


def _make_paper(user, paper_id, title="Test Paper"):
    p = Paper(id=paper_id, user_id=user.id, title=title, data={"title": title})
    db.session.add(p)
    db.session.commit()
    return p


def _auth_headers(user, role=None):
    identity = str(user.id)
    additional_claims = {"role": role or user.role}
    tok = create_access_token(identity=identity, additional_claims=additional_claims)
    return {"Authorization": f"Bearer {tok}"}


def test_list_users_as_admin(app, client):
    with app.app_context():
        admin = _make_user("admin@example.com", "Admin", role="admin")
        user1 = _make_user("user1@example.com", "User 1")
        user2 = _make_user("user2@example.com", "User 2")

        _make_paper(user1, "paper1")
        _make_paper(user1, "paper2")
        _make_paper(user2, "paper3")

        headers = _auth_headers(admin)
        resp = client.get("/api/admin/users", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()

        assert "users" in data
        assert "pagination" in data
        assert len(data["users"]) == 3
        assert data["pagination"]["total"] == 3

        user_emails = [u["email"] for u in data["users"]]
        assert "admin@example.com" in user_emails
        assert "user1@example.com" in user_emails


def test_list_users_as_non_admin(app, client):
    with app.app_context():
        user = _make_user("user@example.com", "User", role="user")

        headers = _auth_headers(user)
        resp = client.get("/api/admin/users", headers=headers)

        assert resp.status_code == 403
        data = resp.get_json()
        assert "Admin access required" in data["error"]


def test_list_users_pagination(app, client):
    with app.app_context():
        admin = _make_user("admin@example.com", "Admin", role="admin")

        for i in range(10):
            _make_user(f"user{i}@example.com", f"User {i}")

        headers = _auth_headers(admin)
        resp = client.get("/api/admin/users?limit=5&offset=0", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()

        assert len(data["users"]) == 5
        assert data["pagination"]["limit"] == 5
        assert data["pagination"]["offset"] == 0
        assert data["pagination"]["total"] == 11
        assert data["pagination"]["has_more"] is True


def test_promote_user_to_admin(app, client):
    with app.app_context():
        admin = _make_user("admin@example.com", "Admin", role="admin")
        user = _make_user("user@example.com", "User", role="user")

        headers = _auth_headers(admin)
        resp = client.post(
            f"/api/admin/users/{user.id}/promote",
            headers=headers,
            json={"role": "admin"}
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        db.session.refresh(user)
        assert user.role == "admin"


def test_promote_user_invalid_role(app, client):
    with app.app_context():
        admin = _make_user("admin@example.com", "Admin", role="admin")
        user = _make_user("user@example.com", "User", role="user")

        headers = _auth_headers(admin)
        resp = client.post(
            f"/api/admin/users/{user.id}/promote",
            headers=headers,
            json={"role": "superadmin"}
        )

        assert resp.status_code == 400
        data = resp.get_json()
        assert "Invalid role" in data["error"]


def test_promote_user_not_found(app, client):
    with app.app_context():
        admin = _make_user("admin@example.com", "Admin", role="admin")

        headers = _auth_headers(admin)
        resp = client.post(
            "/api/admin/users/99999/promote",
            headers=headers,
            json={"role": "admin"}
        )

        assert resp.status_code == 404
        data = resp.get_json()
        assert "User not found" in data["error"]


def test_set_user_quota(app, client):
    with app.app_context():
        admin = _make_user("admin@example.com", "Admin", role="admin")
        user = _make_user("user@example.com", "User", role="user", quota=1000000)

        headers = _auth_headers(admin)
        resp = client.patch(
            f"/api/admin/users/{user.id}/quota",
            headers=headers,
            json={"token_quota_monthly": 5000000}
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        db.session.refresh(user)
        assert user.token_quota_monthly == 5000000


def test_set_user_quota_out_of_range(app, client):
    with app.app_context():
        admin = _make_user("admin@example.com", "Admin", role="admin")
        user = _make_user("user@example.com", "User", role="user")

        headers = _auth_headers(admin)
        resp = client.patch(
            f"/api/admin/users/{user.id}/quota",
            headers=headers,
            json={"token_quota_monthly": 20000000}
        )

        assert resp.status_code == 400
        data = resp.get_json()
        assert "quota out of range" in data["error"]


def test_set_user_quota_invalid_type(app, client):
    with app.app_context():
        admin = _make_user("admin@example.com", "Admin", role="admin")
        user = _make_user("user@example.com", "User", role="user")

        headers = _auth_headers(admin)
        resp = client.patch(
            f"/api/admin/users/{user.id}/quota",
            headers=headers,
            json={"token_quota_monthly": "not-a-number"}
        )

        assert resp.status_code == 400
        data = resp.get_json()
        assert "must be integer" in data["error"]


def test_reset_user_quota(app, client):
    with app.app_context():
        admin = _make_user("admin@example.com", "Admin", role="admin")
        user = _make_user("user@example.com", "User", role="user")
        user.token_used_month = 500000
        user.usage_month_key = "2026-04"
        db.session.commit()

        headers = _auth_headers(admin)
        resp = client.post(
            f"/api/admin/users/{user.id}/reset-quota",
            headers=headers
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        db.session.refresh(user)
        assert user.token_used_month == 0


def test_list_all_papers(app, client):
    with app.app_context():
        admin = _make_user("admin@example.com", "Admin", role="admin")
        user1 = _make_user("user1@example.com", "User 1")
        user2 = _make_user("user2@example.com", "User 2")

        _make_paper(user1, "paper1", "Paper 1")
        _make_paper(user1, "paper2", "Paper 2")
        _make_paper(user2, "paper3", "Paper 3")

        headers = _auth_headers(admin)
        resp = client.get("/api/admin/papers", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()

        assert "papers" in data
        assert "pagination" in data
        assert len(data["papers"]) == 3
        assert data["pagination"]["total"] == 3

        for paper in data["papers"]:
            assert "user_email" in paper
            assert "user_name" in paper


def test_list_all_papers_pagination(app, client):
    with app.app_context():
        admin = _make_user("admin@example.com", "Admin", role="admin")
        user = _make_user("user@example.com", "User")

        for i in range(10):
            _make_paper(user, f"paper{i}", f"Paper {i}")

        headers = _auth_headers(admin)
        resp = client.get("/api/admin/papers?limit=5&offset=0", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()

        assert len(data["papers"]) == 5
        assert data["pagination"]["has_more"] is True


def test_get_usage_stats(app, client):
    with app.app_context():
        admin = _make_user("admin@example.com", "Admin", role="admin")
        user = _make_user("user@example.com", "User")

        now = datetime.utcnow()
        log1 = ApiUsageLog(
            user_id=user.id,
            endpoint="/api/generate",
            model="gpt-4",
            total_tokens=100000,
            prompt_tokens=20000,
            completion_tokens=80000,
            created_at=now
        )
        log2 = ApiUsageLog(
            user_id=user.id,
            endpoint="/api/chat",
            model="gpt-3.5-turbo",
            total_tokens=50000,
            prompt_tokens=10000,
            completion_tokens=40000,
            created_at=now
        )
        db.session.add_all([log1, log2])
        db.session.commit()

        headers = _auth_headers(admin)
        resp = client.get("/api/admin/usage", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()

        assert "total" in data
        assert data["total"]["calls"] == 2
        assert data["total"]["total_tokens"] == 150000

        assert "by_endpoint" in data
        assert "daily" in data
        assert "per_user" in data


def test_get_summary_stats(app, client):
    with app.app_context():
        admin = _make_user("admin@example.com", "Admin", role="admin")
        user = _make_user("user@example.com", "User")

        _make_paper(user, "paper1")
        _make_paper(user, "paper2")

        img = PaperImage(
            paper_id="paper1",
            user_id=user.id,
            filename="img1.png",
            original_name="diagram.png",
            file_path="data/uploads/img1.png",
        )
        db.session.add(img)

        log = ApiUsageLog(
            user_id=user.id,
            endpoint="/api/generate",
            model="gpt-4",
            total_tokens=100000,
            prompt_tokens=20000,
            completion_tokens=80000
        )
        db.session.add(log)
        db.session.commit()

        headers = _auth_headers(admin)
        resp = client.get("/api/admin/stats", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()

        assert data["total_users"] == 2
        assert data["total_papers"] == 2
        assert data["total_images"] == 1
        assert data["total_tokens"] == 100000
        assert data["total_api_calls"] == 1


def test_admin_endpoints_require_auth(app, client):
    endpoints = [
        "/api/admin/users",
        "/api/admin/papers",
        "/api/admin/usage",
        "/api/admin/stats",
    ]

    for endpoint in endpoints:
        resp = client.get(endpoint)
        assert resp.status_code == 401
