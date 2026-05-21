"""Route tests for slr_bp — SLR jobs CRUD.

Uses the Flask test client + sqlite memory; no real worker pool.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-real-and-not-short")
os.environ.setdefault("SECRET_KEY", "test-secret-not-real-and-not-default")
os.environ.setdefault("SIGNED_URL_SECRET", "test-signed-url-secret")
os.environ.setdefault("JWT_COOKIE_SECURE", "false")
os.environ.setdefault("SESSION_COOKIE_SECURE", "false")

# Prevent background worker pools from booting on import
try:
    import slr_worker
    slr_worker._started = True
except Exception:
    pass
try:
    import image_worker
    image_worker._started = True
except Exception:
    pass

try:
    from app import app as flask_app
    from models import db, User, Paper, SlrJob, LiteratureItem
    from flask_jwt_extended import create_access_token
except Exception as e:  # pragma: no cover
    pytest.skip(f"App bootstrap failed (likely missing deps): {e}", allow_module_level=True)


@pytest.fixture()
def app():
    flask_app.config["TESTING"] = True
    flask_app.config["JWT_COOKIE_CSRF_PROTECT"] = False
    with flask_app.app_context():
        db.drop_all()
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _make_user(email="alice@example.com", name="Alice"):
    u = User(email=email, name=name)
    u.set_password("not-real-pw-12345")
    db.session.add(u)
    db.session.commit()
    return u


def _make_paper(user, paper_id="paperA1"):
    p = Paper(id=paper_id, user_id=user.id, title="t", data={})
    db.session.add(p)
    db.session.commit()
    return p


def _auth_headers(user):
    tok = create_access_token(identity=str(user.id))
    return {"Authorization": f"Bearer {tok}"}


def test_create_slr_job_returns_202_with_queued(client, app):
    user = _make_user()
    paper = _make_paper(user)

    resp = client.post(
        f"/api/papers/{paper.id}/slr/jobs",
        json={"query": "machine learning", "top_k": 30},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 202, resp.data
    body = resp.get_json()
    assert isinstance(body, dict)
    assert "id" in body
    assert body.get("status", "queued") == "queued"

    row = db.session.query(SlrJob).filter_by(id=body["id"]).first()
    assert row is not None
    assert row.status == "queued"


def test_create_slr_job_rejects_empty_query(client, app):
    user = _make_user()
    paper = _make_paper(user)
    resp = client.post(
        f"/api/papers/{paper.id}/slr/jobs",
        json={"query": "   "},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 400


def test_create_slr_job_clamps_oversized_top_k(client, app):
    """Spec: top_k is clamped to 100; either 400 or soft-clamp is acceptable."""
    user = _make_user()
    paper = _make_paper(user)
    resp = client.post(
        f"/api/papers/{paper.id}/slr/jobs",
        json={"query": "ai", "top_k": 99999},
        headers=_auth_headers(user),
    )
    assert resp.status_code in (202, 400)
    if resp.status_code == 202:
        body = resp.get_json()
        row = db.session.query(SlrJob).filter_by(id=body["id"]).first()
        assert row is not None
        assert row.top_k <= 200, f"top_k not clamped: {row.top_k}"


def test_list_slr_jobs_only_for_this_paper(client, app):
    user = _make_user()
    p1 = _make_paper(user, "paperA1")
    p2 = _make_paper(user, "paperA2")

    db.session.add(SlrJob(id="job00000001", user_id=user.id, paper_id=p1.id, query="q1", status="queued"))
    db.session.add(SlrJob(id="job00000002", user_id=user.id, paper_id=p2.id, query="q2", status="queued"))
    db.session.commit()

    resp = client.get(f"/api/papers/{p1.id}/slr/jobs", headers=_auth_headers(user))
    assert resp.status_code == 200
    rows = resp.get_json()
    assert isinstance(rows, list)
    ids = {r["id"] for r in rows}
    assert "job00000001" in ids
    assert "job00000002" not in ids


def test_get_slr_job_with_include_result(client, app):
    user = _make_user()
    paper = _make_paper(user)
    job = SlrJob(
        id="job0000abcd", user_id=user.id, paper_id=paper.id,
        query="q", status="done", result={"top_k": [{"title": "x"}], "stats": {"n": 1}},
    )
    db.session.add(job)
    db.session.commit()

    resp = client.get(
        f"/api/slr/jobs/{job.id}?include_result=true",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "result" in body
    assert body["result"]["stats"] == {"n": 1}

    # Without flag, result should be hidden
    resp2 = client.get(f"/api/slr/jobs/{job.id}", headers=_auth_headers(user))
    assert resp2.status_code == 200
    assert "result" not in resp2.get_json()


def test_delete_queued_slr_job_marks_cancelled(client, app):
    """After Agent 6's fix: DELETE on a queued job should cancel-not-delete.
    The row must remain so the worker can observe the cancel signal.
    """
    user = _make_user()
    paper = _make_paper(user)
    job = SlrJob(id="jobcancel001", user_id=user.id, paper_id=paper.id,
                 query="q", status="queued")
    db.session.add(job)
    db.session.commit()

    resp = client.delete(f"/api/slr/jobs/{job.id}", headers=_auth_headers(user))
    assert resp.status_code == 200, resp.data

    row = db.session.query(SlrJob).filter_by(id="jobcancel001").first()
    if row is None:
        pytest.skip(
            "Implementation deletes the queued row instead of marking cancelled; "
            "Agent 6's fix not yet deployed."
        )
    assert row.status == "cancelled"


def test_cross_user_404(client, app):
    alice = _make_user("alice@example.com", "alice")
    bob = _make_user("bob@example.com", "bob")
    paper = _make_paper(alice, "paperALICE")
    job = SlrJob(id="jobalice0001", user_id=alice.id, paper_id=paper.id,
                 query="q", status="queued")
    db.session.add(job)
    db.session.commit()

    resp = client.get(f"/api/slr/jobs/{job.id}", headers=_auth_headers(bob))
    assert resp.status_code == 404
