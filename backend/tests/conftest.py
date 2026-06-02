"""Pytest config — isolate from system pytest plugins (e.g. ROS launch_testing).

Also CRITICAL: force test DB env vars BEFORE any test or app module imports.
Without this, .env is loaded at app-import time and tests would happily
``db.drop_all()`` against the production Postgres database (this happened
once — never again). We use plain assignment, not ``setdefault``, so any
inherited value (from .env, shell, or pm2) is overridden.
"""

import os

os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

# Force in-memory test DB regardless of any inherited DATABASE_URL.
# Tests that need a real DB must be opt-in (e.g. an integration marker).
_db = os.environ.get("DATABASE_URL", "")
if not _db.startswith("sqlite:"):
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Required-by-app secrets — give safe test defaults so app.py import doesn't
# RuntimeError when the host .env hasn't been loaded yet.
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-for-production")
os.environ.setdefault("SECRET_KEY", "test-flask-secret-not-for-production")
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("ENABLE_CAPTCHA", "false")

# Belt-and-suspenders: refuse to run against any host that looks like a real DB.
_url = os.environ["DATABASE_URL"]
if not _url.startswith("sqlite:"):
    raise RuntimeError(f"Test suite refuses to run against non-sqlite DATABASE_URL: {_url!r}")


# ── Pytest Fixtures ──────────────────────────────────────────────────────────
import pytest

from app import app as flask_app
from database.models import User, db


@pytest.fixture(scope="session")
def app():
    """Create Flask app configured for testing."""
    flask_app.config.update(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "JWT_COOKIE_CSRF_PROTECT": False,
            "RATELIMIT_ENABLED": False,  # Disable rate limiting for tests
        }
    )

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope="function")
def client(app):
    """Create test client for making requests."""
    return app.test_client()


@pytest.fixture(scope="function")
def db_session(app):
    """Create clean database session for each test."""
    with app.app_context():
        connection = db.engine.connect()
        transaction = connection.begin()

        yield db.session

        transaction.rollback()
        connection.close()


@pytest.fixture
def test_user(app):
    """Create test user for authentication tests."""
    with app.app_context():
        user = User(name="Test User", email="test@example.com", role="user")
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.commit()

        yield user

        db.session.delete(user)
        db.session.commit()


@pytest.fixture
def admin_user(app):
    """Create admin user for admin tests."""
    with app.app_context():
        user = User(name="Admin User", email="admin@example.com", role="admin")
        user.set_password("AdminPassword123!")
        db.session.add(user)
        db.session.commit()

        yield user

        db.session.delete(user)
        db.session.commit()


@pytest.fixture
def test_paper(app, test_user):
    """Create test paper for CRUD tests."""
    from database.models import Paper

    with app.app_context():
        paper = Paper(
            id="test-paper-1",
            user_id=test_user.id,
            title="Test Paper",
            data={
                "title": "Test Paper",
                "abstract": "This is a test paper abstract.",
                "sections": [{"title": "Introduction", "content": "Test content"}],
            },
        )
        db.session.add(paper)
        db.session.commit()

        yield paper

        db.session.delete(paper)
        db.session.commit()


@pytest.fixture
def other_user(app):
    """Create another user for user isolation tests."""
    with app.app_context():
        user = User(name="Other User", email="other@example.com", role="user")
        user.set_password("OtherPassword123!")
        db.session.add(user)
        db.session.commit()

        yield user

        db.session.delete(user)
        db.session.commit()


@pytest.fixture
def other_user_paper(app, other_user):
    """Create paper owned by other_user for isolation tests."""
    from database.models import Paper

    with app.app_context():
        paper = Paper(
            id="other-paper-1",
            user_id=other_user.id,
            title="Other User Paper",
            data={"title": "Other User Paper", "abstract": "This paper belongs to another user."},
        )
        db.session.add(paper)
        db.session.commit()

        yield paper

        db.session.delete(paper)
        db.session.commit()


@pytest.fixture
def auth_token(app, test_user):
    """Generate JWT access token for test_user without hitting login endpoint."""
    from flask_jwt_extended import create_access_token

    with app.app_context():
        token = create_access_token(identity=str(test_user.id))
        return token


@pytest.fixture
def auth_headers(auth_token):
    """Generate authorization headers with Bearer token."""
    return {"Authorization": f"Bearer {auth_token}"}
