"""
Unit tests for jobs_bp — Job management and SSE streaming endpoints.
Note: Redis and RQ are mocked to avoid external dependencies.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-real-and-not-short")
os.environ.setdefault("SECRET_KEY", "test-secret-not-real-and-not-default")
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

try:
    from flask import Flask
    from flask_jwt_extended import JWTManager, create_access_token
    from sqlalchemy import JSON

    from api.jobs_bp import jobs_bp
    from database.models import AiJob, Paper, User, db

    Paper.__table__.c.data.type = JSON()
except Exception as e:
    pytest.skip(f"Jobs blueprint bootstrap failed: {e}", allow_module_level=True)


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
    flask_app.register_blueprint(jobs_bp)

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def mock_redis():
    with patch("api.jobs_bp._REDIS") as mock:
        mock.publish = MagicMock()
        mock.setex = MagicMock()
        mock.delete = MagicMock()
        yield mock


def _make_user(email="user@example.com", name="User", role="user"):
    u = User(email=email, name=name, role=role)
    u.set_password("test-password-123")
    db.session.add(u)
    db.session.commit()
    return u


def _make_paper(user, paper_id="paper1", title="Test Paper"):
    p = Paper(id=paper_id, user_id=user.id, title=title, data={"title": title})
    db.session.add(p)
    db.session.commit()
    return p


def _auth_headers(user):
    tok = create_access_token(identity=str(user.id))
    return {"Authorization": f"Bearer {tok}"}


@patch("api.jobs_bp.Queue")
def test_enqueue_generate_success(mock_queue, app, client, mock_redis):
    with app.app_context():
        user = _make_user()
        paper = _make_paper(user)

        mock_q = MagicMock()
        mock_queue.return_value = mock_q

        headers = _auth_headers(user)
        resp = client.post(
            f"/api/papers/{paper.id}/generate",
            headers=headers,
            json={"prompt": "Write a paper about AI"}
        )

        assert resp.status_code == 200
        data = resp.get_json()

        assert "job_id" in data
        assert data["status"] == "queued"

        job = AiJob.query.filter_by(paper_id=paper.id).first()
        assert job is not None
        assert job.kind == "generate_paper"
        assert job.status == "queued"
        assert job.prompt == "Write a paper about AI"


def test_enqueue_generate_missing_prompt(app, client):
    with app.app_context():
        user = _make_user()
        paper = _make_paper(user)

        headers = _auth_headers(user)
        resp = client.post(
            f"/api/papers/{paper.id}/generate",
            headers=headers,
            json={}
        )

        assert resp.status_code == 400
        data = resp.get_json()
        assert "prompt required" in data["error"]


def test_enqueue_generate_paper_not_found(app, client):
    with app.app_context():
        user = _make_user()

        headers = _auth_headers(user)
        resp = client.post(
            "/api/papers/nonexistent/generate",
            headers=headers,
            json={"prompt": "Test"}
        )

        assert resp.status_code == 404
        data = resp.get_json()
        assert "paper not found" in data["error"]


def test_get_job_success(app, client):
    with app.app_context():
        user = _make_user()
        paper = _make_paper(user)

        job = AiJob(
            id="job123",
            user_id=user.id,
            paper_id=paper.id,
            kind="generate_paper",
            status="running",
            progress=50,
            stage="section_2",
            prompt="Test prompt"
        )
        db.session.add(job)
        db.session.commit()

        headers = _auth_headers(user)
        resp = client.get(f"/api/jobs/{job.id}", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()

        assert data["id"] == "job123"
        assert data["status"] == "running"
        assert data["progress"] == 50
        assert data["stage"] == "section_2"


def test_get_job_not_found(app, client):
    with app.app_context():
        user = _make_user()

        headers = _auth_headers(user)
        resp = client.get("/api/jobs/nonexistent", headers=headers)

        assert resp.status_code == 404
        data = resp.get_json()
        assert "not found" in data["error"]


def test_cancel_job_success(app, client, mock_redis):
    with app.app_context():
        user = _make_user()
        paper = _make_paper(user)

        job = AiJob(
            id="job123",
            user_id=user.id,
            paper_id=paper.id,
            kind="generate_paper",
            status="running",
            progress=30
        )
        db.session.add(job)
        db.session.commit()

        headers = _auth_headers(user)
        resp = client.post(f"/api/jobs/{job.id}/cancel", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True

        db.session.refresh(job)
        assert job.status == "cancelled"


def test_cancel_job_already_done(app, client, mock_redis):
    with app.app_context():
        user = _make_user()
        paper = _make_paper(user)

        job = AiJob(
            id="job123",
            user_id=user.id,
            paper_id=paper.id,
            kind="generate_paper",
            status="done",
            progress=100
        )
        db.session.add(job)
        db.session.commit()

        headers = _auth_headers(user)
        resp = client.post(f"/api/jobs/{job.id}/cancel", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["status"] == "done"


def test_active_jobs(app, client):
    with app.app_context():
        user = _make_user()
        paper = _make_paper(user)

        job1 = AiJob(
            id="job1",
            user_id=user.id,
            paper_id=paper.id,
            kind="generate_paper",
            status="running",
            progress=30
        )
        job2 = AiJob(
            id="job2",
            user_id=user.id,
            paper_id=paper.id,
            kind="generate_paper",
            status="queued",
            progress=0
        )
        job3 = AiJob(
            id="job3",
            user_id=user.id,
            paper_id=paper.id,
            kind="generate_paper",
            status="done",
            progress=100
        )
        db.session.add_all([job1, job2, job3])
        db.session.commit()

        headers = _auth_headers(user)
        resp = client.get(f"/api/papers/{paper.id}/active-jobs", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()

        assert "jobs" in data
        assert len(data["jobs"]) == 2
        job_ids = [j["id"] for j in data["jobs"]]
        assert "job1" in job_ids
        assert "job2" in job_ids
        assert "job3" not in job_ids


def test_ai_jobs_active_found(app, client):
    with app.app_context():
        user = _make_user()
        paper = _make_paper(user)

        job = AiJob(
            id="job1",
            user_id=user.id,
            paper_id=paper.id,
            kind="generate_paper",
            status="running",
            progress=50
        )
        db.session.add(job)
        db.session.commit()

        headers = _auth_headers(user)
        resp = client.get(f"/api/papers/{paper.id}/ai-jobs/active", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()

        assert data["job"] is not None
        assert data["job"]["id"] == "job1"


def test_ai_jobs_active_not_found(app, client):
    with app.app_context():
        user = _make_user()
        paper = _make_paper(user)

        headers = _auth_headers(user)
        resp = client.get(f"/api/papers/{paper.id}/ai-jobs/active", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()

        assert data["job"] is None


def test_ai_jobs_cancel(app, client, mock_redis):
    with app.app_context():
        user = _make_user()
        paper = _make_paper(user)

        job = AiJob(
            id="job1",
            user_id=user.id,
            paper_id=paper.id,
            kind="generate_paper",
            status="running",
            progress=30
        )
        db.session.add(job)
        db.session.commit()

        headers = _auth_headers(user)
        resp = client.post(f"/api/ai-jobs/{job.id}/cancel", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()

        assert "job" in data
        assert data["job"]["status"] == "cancelled"


def test_ai_jobs_resume(app, client, mock_redis):
    with app.app_context():
        user = _make_user()
        paper = _make_paper(user)

        job = AiJob(
            id="job1",
            user_id=user.id,
            paper_id=paper.id,
            kind="generate_paper",
            status="paused",
            progress=50,
            result={
                "chunks_done": ["outline", "section_1"],
                "partial_paper": {"outline": "test"}
            }
        )
        db.session.add(job)
        db.session.commit()

        with patch("api.jobs_bp._enqueue_resume"):
            headers = _auth_headers(user)
            resp = client.post(f"/api/ai-jobs/{job.id}/resume", headers=headers)

            assert resp.status_code == 200
            data = resp.get_json()

            assert "job" in data
            assert "resume_state" in data

            db.session.refresh(job)
            assert job.status == "queued"
            assert job.error is None


def test_ai_jobs_resume_invalid_status(app, client):
    with app.app_context():
        user = _make_user()
        paper = _make_paper(user)

        job = AiJob(
            id="job1",
            user_id=user.id,
            paper_id=paper.id,
            kind="generate_paper",
            status="running",
            progress=50
        )
        db.session.add(job)
        db.session.commit()

        headers = _auth_headers(user)
        resp = client.post(f"/api/ai-jobs/{job.id}/resume", headers=headers)

        assert resp.status_code == 409
        data = resp.get_json()
        assert "cannot resume" in data["error"]


def test_ai_jobs_retry_section(app, client, mock_redis):
    with app.app_context():
        user = _make_user()
        paper = _make_paper(user)

        job = AiJob(
            id="job1",
            user_id=user.id,
            paper_id=paper.id,
            kind="generate_paper",
            status="done",
            progress=100,
            result={
                "chunks_done": ["outline", "section_1", "section_2", "combine"],
                "partial_paper": {
                    "outline": "test",
                    "sections": [{"title": "Intro"}, {"title": "Methods"}]
                }
            }
        )
        db.session.add(job)
        db.session.commit()

        with patch("api.jobs_bp._enqueue_resume"):
            headers = _auth_headers(user)
            resp = client.post(
                f"/api/ai-jobs/{job.id}/retry-section",
                headers=headers,
                json={"stage": "section_2"}
            )

            assert resp.status_code == 200
            resp.get_json()

            db.session.refresh(job)
            assert job.status == "queued"
            assert "section_2" not in job.result["chunks_done"]
            assert "combine" not in job.result["chunks_done"]


def test_ai_jobs_recent(app, client):
    with app.app_context():
        user = _make_user()
        paper = _make_paper(user)

        now = datetime.now(timezone.utc)

        for i in range(5):
            job = AiJob(
                id=f"job{i}",
                user_id=user.id,
                paper_id=paper.id,
                kind="generate_paper",
                status="done",
                progress=100,
                started_at=now
            )
            db.session.add(job)
        db.session.commit()

        headers = _auth_headers(user)
        resp = client.get("/api/me/ai-jobs/recent", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()

        assert "jobs" in data
        assert len(data["jobs"]) == 5


def test_ai_jobs_recent_with_filters(app, client):
    with app.app_context():
        user = _make_user()
        paper = _make_paper(user)

        now = datetime.now(timezone.utc)

        job1 = AiJob(
            id="job1",
            user_id=user.id,
            paper_id=paper.id,
            kind="generate_paper",
            status="done",
            progress=100,
            started_at=now
        )
        job2 = AiJob(
            id="job2",
            user_id=user.id,
            paper_id=paper.id,
            kind="generate_paper",
            status="error",
            progress=50,
            started_at=now
        )
        db.session.add_all([job1, job2])
        db.session.commit()

        headers = _auth_headers(user)
        resp = client.get("/api/me/ai-jobs/recent?status=error", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()

        assert len(data["jobs"]) == 1
        assert data["jobs"][0]["id"] == "job2"
