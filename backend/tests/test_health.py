"""
Tests for Health Check API
=====================================
Unit tests for health monitoring endpoints with proper fixtures.
"""

import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-real")
os.environ.setdefault("SECRET_KEY", "test-secret-not-real")
os.environ.setdefault("FLASK_ENV", "testing")

try:
    from flask import Flask

    from api.health_bp import health_bp
    from database.models import db
except Exception as e:
    pytest.skip(f"Health blueprint bootstrap failed: {e}", allow_module_level=True)


@pytest.fixture()
def app(tmp_path):
    """Create minimal Flask app for testing health endpoints."""
    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(flask_app)
    flask_app.register_blueprint(health_bp)

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    """Create test client from app fixture."""
    return app.test_client()


def test_health_basic(client):
    """Test basic health check endpoint."""
    response = client.get('/api/health')
    assert response.status_code == 200

    data = response.get_json()
    assert data['status'] == 'healthy'
    assert 'timestamp' in data
    assert data['service'] == 'papergenerator'


def test_health_detailed(client):
    """Test detailed health check endpoint."""
    response = client.get('/api/health/detailed')
    assert response.status_code in [200, 503]

    data = response.get_json()
    assert 'status' in data
    assert 'timestamp' in data
    assert 'service' in data
    assert 'uptime_seconds' in data
    assert 'checks' in data

    checks = data['checks']
    assert 'database' in checks
    assert 'disk' in checks
    assert 'memory' in checks


def test_health_database_check(client):
    """Test database connectivity check."""
    response = client.get('/api/health/detailed')
    data = response.get_json()

    db_check = data['checks']['database']
    assert 'status' in db_check
    assert db_check['status'] == 'healthy'
    assert 'message' in db_check


def test_health_disk_check(client):
    """Test disk space check."""
    response = client.get('/api/health/detailed')
    data = response.get_json()

    disk_check = data['checks']['disk']
    assert 'status' in disk_check
    assert 'total_gb' in disk_check
    assert 'free_gb' in disk_check
    assert 'percent_used' in disk_check
    assert disk_check['free_gb'] > 0


def test_health_memory_check(client):
    """Test memory usage check."""
    response = client.get('/api/health/detailed')
    data = response.get_json()

    memory_check = data['checks']['memory']
    assert 'status' in memory_check
