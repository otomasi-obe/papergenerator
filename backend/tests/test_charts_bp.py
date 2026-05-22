"""Route tests for charts_bp — POST /api/papers/<paper_id>/charts.

Spins up a *minimal* Flask app (sqlite memory) so we don't pay for the full
backend bootstrap and we don't fight whatever postgres state happens to be
loaded on the host. Mocks chart_generator.generate_chart so matplotlib I/O
stays out of the test path.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Required env BEFORE we import any backend module that touches Flask config.
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-real-and-not-short")
os.environ.setdefault("SECRET_KEY", "test-secret-not-real-and-not-default")
os.environ.setdefault("SIGNED_URL_SECRET", "test-signed-url-secret")
os.environ.setdefault("JWT_COOKIE_SECURE", "false")
os.environ.setdefault("SESSION_COOKIE_SECURE", "false")

try:
    from flask import Flask
    from flask_jwt_extended import JWTManager, create_access_token
    from sqlalchemy import JSON
    from charts_bp import charts_bp
    from models import Paper, PaperImage, User, db
    # Swap JSONB for JSON on the Paper.data column so sqlite can render
    # CREATE TABLE. The model itself isn't reloaded at runtime in the real
    # backend, so this is purely a test-side compat shim.
    Paper.__table__.c.data.type = JSON()
except Exception as e:  # pragma: no cover
    pytest.skip(f"Charts blueprint bootstrap failed: {e}", allow_module_level=True)


# ─── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture()
def app(tmp_path):
    flask_app = Flask(__name__)
    # Critical: make uploads/ sit inside tmp_path so the blueprint's
    # safe_paper_dir doesn't write to the real backend uploads folder.
    flask_app.root_path = str(tmp_path)
    flask_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY=os.environ["JWT_SECRET_KEY"],
        JWT_COOKIE_CSRF_PROTECT=False,
        JWT_TOKEN_LOCATION=["headers"],
        SIGNED_URL_SECRET=os.environ["SIGNED_URL_SECRET"],
    )
    JWTManager(flask_app)
    db.init_app(flask_app)
    flask_app.register_blueprint(charts_bp)

    with flask_app.app_context():
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


def _make_paper(user, paper_id="paperC1"):
    p = Paper(id=paper_id, user_id=user.id, title="t", data={})
    db.session.add(p)
    db.session.commit()
    return p


def _auth_headers(user):
    tok = create_access_token(identity=str(user.id))
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture()
def fake_chart_png(tmp_path):
    """Return a real PNG file path. The blueprint moves it into uploads/<paper_id>/."""
    p = tmp_path / "fake_chart.png"
    p.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        b"\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return str(p)


# ─── tests ───────────────────────────────────────────────────────────────


def test_create_chart_unauthorized(client):
    """No JWT → 401 (jwt_required rejects before any handler logic runs)."""
    resp = client.post(
        "/api/papers/paperC1/charts",
        json={"kind": "line", "title": "t", "data": [[1, 2, 3]]},
    )
    assert resp.status_code in (401, 422), resp.data


def test_create_chart_invalid_paper_id(client, app):
    user = _make_user()
    resp = client.post(
        "/api/papers/bad..id!!/charts",
        json={"kind": "line", "title": "t", "data": [[1, 2, 3]]},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 400, resp.data
    body = resp.get_json()
    assert body["code"] == "BAD_REQUEST"


def test_create_chart_paper_not_found(client, app):
    user = _make_user()
    resp = client.post(
        "/api/papers/missing01/charts",
        json={"kind": "line", "title": "t", "data": [[1, 2, 3]]},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 404, resp.data
    assert resp.get_json()["code"] == "NOT_FOUND"


def test_create_chart_invalid_kind(client, app):
    user = _make_user()
    paper = _make_paper(user)
    resp = client.post(
        f"/api/papers/{paper.id}/charts",
        json={"kind": "doughnut", "title": "t", "data": [[1, 2, 3]]},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 400, resp.data
    assert resp.get_json()["code"] == "BAD_KIND"


def test_create_chart_missing_title(client, app):
    user = _make_user()
    paper = _make_paper(user)
    resp = client.post(
        f"/api/papers/{paper.id}/charts",
        json={"kind": "line", "data": [[1, 2, 3]]},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 400, resp.data
    assert resp.get_json()["code"] == "BAD_SPEC"


def test_create_chart_empty_data(client, app):
    user = _make_user()
    paper = _make_paper(user)
    resp = client.post(
        f"/api/papers/{paper.id}/charts",
        json={"kind": "line", "title": "t", "data": []},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 400, resp.data
    assert resp.get_json()["code"] == "BAD_SPEC"


def test_create_chart_bad_x_data_type(client, app):
    user = _make_user()
    paper = _make_paper(user)
    resp = client.post(
        f"/api/papers/{paper.id}/charts",
        json={"kind": "line", "title": "t", "data": [[1, 2]], "x_data": "not-a-list"},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 400, resp.data
    assert resp.get_json()["code"] == "BAD_SPEC"


def test_create_chart_bad_series_labels_type(client, app):
    user = _make_user()
    paper = _make_paper(user)
    resp = client.post(
        f"/api/papers/{paper.id}/charts",
        json={"kind": "line", "title": "t", "data": [[1, 2]], "series_labels": "A"},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 400, resp.data
    assert resp.get_json()["code"] == "BAD_SPEC"


def test_create_chart_happy_path(client, app, fake_chart_png):
    """Full happy path: 201, response carries image_id/filename/url, and a
    PaperImage row is committed to the DB."""
    user = _make_user()
    paper = _make_paper(user)

    with patch("charts_bp.generate_chart", return_value=fake_chart_png):
        resp = client.post(
            f"/api/papers/{paper.id}/charts",
            json={
                "kind": "line",
                "title": "Energy over time",
                "xlabel": "t",
                "ylabel": "v",
                "data": [[1, 2, 3, 4]],
                "series_labels": ["A"],
            },
            headers=_auth_headers(user),
        )

    assert resp.status_code == 201, resp.data
    body = resp.get_json()
    assert "image_id" in body
    assert body["filename"]
    assert body["url"].startswith(f"/api/images/{paper.id}/")
    assert body["kind"] == "line"

    img = PaperImage.query.filter_by(id=body["image_id"]).first()
    assert img is not None
    assert img.paper_id == paper.id
    assert img.user_id == user.id
    assert img.filename == body["filename"]


def test_create_chart_propagates_value_error(client, app):
    """generate_chart raises ValueError on bad spec → 400 BAD_SPEC."""
    user = _make_user()
    paper = _make_paper(user)

    def boom(*_a, **_kw):
        raise ValueError("scatter requires x_data and data")

    with patch("charts_bp.generate_chart", side_effect=boom):
        resp = client.post(
            f"/api/papers/{paper.id}/charts",
            json={"kind": "scatter", "title": "t", "data": [[1, 2, 3]]},
            headers=_auth_headers(user),
        )

    assert resp.status_code == 400, resp.data
    assert resp.get_json()["code"] == "BAD_SPEC"


def test_create_chart_propagates_runtime_error(client, app):
    """generate_chart raising a non-ValueError → 500 GENERATE_ERROR."""
    user = _make_user()
    paper = _make_paper(user)

    def boom(*_a, **_kw):
        raise RuntimeError("matplotlib backend missing")

    with patch("charts_bp.generate_chart", side_effect=boom):
        resp = client.post(
            f"/api/papers/{paper.id}/charts",
            json={"kind": "line", "title": "t", "data": [[1, 2]]},
            headers=_auth_headers(user),
        )

    assert resp.status_code == 500, resp.data
    assert resp.get_json()["code"] == "GENERATE_ERROR"


def test_create_chart_cross_user_404(client, app, fake_chart_png):
    """User B must not be able to create a chart in user A's paper."""
    alice = _make_user("alice@example.com", "alice")
    bob = _make_user("bob@example.com", "bob")
    paper = _make_paper(alice, "paperALICE")

    with patch("charts_bp.generate_chart", return_value=fake_chart_png):
        resp = client.post(
            f"/api/papers/{paper.id}/charts",
            json={"kind": "line", "title": "t", "data": [[1, 2]]},
            headers=_auth_headers(bob),
        )

    assert resp.status_code == 404, resp.data
    assert resp.get_json()["code"] == "NOT_FOUND"
