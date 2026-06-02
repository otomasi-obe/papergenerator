"""Tests for slr_bp Literature endpoints."""

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
    from flask_jwt_extended import create_access_token

    from app import app as flask_app
    from database.models import LiteratureItem, Paper, User, db
except Exception as e:  # pragma: no cover
    pytest.skip(f"App bootstrap failed: {e}", allow_module_level=True)


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


def _user(email="lit@example.com", name="Lit"):
    u = User(email=email, name=name)
    u.set_password("not-real-pw-12345")
    db.session.add(u)
    db.session.commit()
    return u


def _paper(user, pid="paperLIT001"):
    p = Paper(id=pid, user_id=user.id, title="t", data={})
    db.session.add(p)
    db.session.commit()
    return p


def _hdr(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


# ─── POST /literature ────────────────────────────────────────────────────


def test_post_literature_requires_title(client, app):
    user = _user()
    paper = _paper(user)
    resp = client.post(
        f"/api/papers/{paper.id}/literature",
        json={"authors": ["x"]},
        headers=_hdr(user),
    )
    assert resp.status_code == 400


def test_post_literature_garbage_doi_stored_as_none(client, app):
    user = _user()
    paper = _paper(user)
    resp = client.post(
        f"/api/papers/{paper.id}/literature",
        json={"title": "T", "doi": "this-is-not-a-doi"},
        headers=_hdr(user),
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert "doi" in (body.get("error") or "").lower()


def test_post_literature_bad_url_stored_as_none(client, app):
    user = _user()
    paper = _paper(user)
    resp = client.post(
        f"/api/papers/{paper.id}/literature",
        json={"title": "T", "url": "javascript:alert(1)"},
        headers=_hdr(user),
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert "url" in (body.get("error") or "").lower()


# ─── PATCH /literature/<id> ──────────────────────────────────────────────


def test_patch_whitelisted_fields_apply(client, app):
    user = _user()
    paper = _paper(user)
    item = LiteratureItem(paper_id=paper.id, user_id=user.id, title="old")
    db.session.add(item)
    db.session.commit()
    item_id = item.id

    resp = client.patch(
        f"/api/papers/{paper.id}/literature/{item_id}",
        json={
            "title": "NEW T",
            "authors": ["A", "B"],
            "summary": "summ",
            "must_read": True,
            "pinned": True,
        },
        headers=_hdr(user),
    )
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body["title"] == "NEW T"
    assert body["authors"] == ["A", "B"]
    assert body["summary"] == "summ"
    assert body["must_read"] is True
    assert body["pinned"] is True


def test_patch_ignores_unknown_keys(client, app):
    user = _user()
    paper = _paper(user)
    item = LiteratureItem(paper_id=paper.id, user_id=user.id, title="x")
    db.session.add(item)
    db.session.commit()

    resp = client.patch(
        f"/api/papers/{paper.id}/literature/{item.id}",
        json={"banana": "🍌", "title": "ok"},
        headers=_hdr(user),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["title"] == "ok"
    assert "banana" not in body


def test_patch_cannot_mutate_protected_fields(client, app):
    user = _user()
    paper = _paper(user)
    item = LiteratureItem(
        paper_id=paper.id,
        user_id=user.id,
        title="x",
        score_total=0.5,
        slr_job_id=None,
    )
    db.session.add(item)
    db.session.commit()
    original_paper_id = item.paper_id

    resp = client.patch(
        f"/api/papers/{paper.id}/literature/{item.id}",
        json={
            "paper_id": "OTHER_PAPER",
            "score_total": 99.9,
            "slr_job_id": "fakejob",
            "title": "new title",
        },
        headers=_hdr(user),
    )
    assert resp.status_code == 200
    db.session.refresh(item)
    assert item.paper_id == original_paper_id
    assert item.score_total == 0.5
    assert item.slr_job_id is None
    assert item.title == "new title"


# ─── DELETE /literature/<id> ─────────────────────────────────────────────


def test_delete_literature_removes_row(client, app):
    user = _user()
    paper = _paper(user)
    item = LiteratureItem(paper_id=paper.id, user_id=user.id, title="kill me")
    db.session.add(item)
    db.session.commit()
    item_id = item.id

    resp = client.delete(
        f"/api/papers/{paper.id}/literature/{item_id}",
        headers=_hdr(user),
    )
    assert resp.status_code == 200

    assert db.session.query(LiteratureItem).filter_by(id=item_id).first() is None


# ─── Cross-user 404 ──────────────────────────────────────────────────────


def test_cross_user_get_returns_404(client, app):
    alice = _user("a@e.com", "a")
    bob = _user("b@e.com", "b")
    paper = _paper(alice, "paperALICE")
    item = LiteratureItem(paper_id=paper.id, user_id=alice.id, title="hers")
    db.session.add(item)
    db.session.commit()

    # Bob cannot read alice's paper -> 404
    r = client.get(f"/api/papers/{paper.id}/literature", headers=_hdr(bob))
    assert r.status_code == 404


def test_cross_user_patch_returns_404(client, app):
    alice = _user("a@e.com", "a")
    bob = _user("b@e.com", "b")
    paper = _paper(alice, "paperALICE2")
    item = LiteratureItem(paper_id=paper.id, user_id=alice.id, title="hers")
    db.session.add(item)
    db.session.commit()

    r = client.patch(
        f"/api/papers/{paper.id}/literature/{item.id}",
        json={"title": "stolen"},
        headers=_hdr(bob),
    )
    assert r.status_code == 404


def test_cross_user_delete_returns_404(client, app):
    alice = _user("a@e.com", "a")
    bob = _user("b@e.com", "b")
    paper = _paper(alice, "paperALICE3")
    item = LiteratureItem(paper_id=paper.id, user_id=alice.id, title="hers")
    db.session.add(item)
    db.session.commit()

    r = client.delete(
        f"/api/papers/{paper.id}/literature/{item.id}",
        headers=_hdr(bob),
    )
    assert r.status_code == 404


# ─── Ordering: pinned first ──────────────────────────────────────────────


def test_get_returns_pinned_items_first(client, app):
    user = _user()
    paper = _paper(user)
    db.session.add(
        LiteratureItem(
            paper_id=paper.id, user_id=user.id, title="plain", pinned=False, score_total=0.9
        )
    )
    db.session.add(
        LiteratureItem(
            paper_id=paper.id, user_id=user.id, title="pinned-low", pinned=True, score_total=0.1
        )
    )
    db.session.commit()

    resp = client.get(f"/api/papers/{paper.id}/literature", headers=_hdr(user))
    assert resp.status_code == 200
    rows = resp.get_json()
    assert len(rows) == 2
    # Pinned must come first regardless of score
    assert rows[0]["pinned"] is True
    assert rows[0]["title"] == "pinned-low"
    assert rows[1]["pinned"] is False
