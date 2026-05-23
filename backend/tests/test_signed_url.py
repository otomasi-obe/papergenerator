"""HMAC signed-URL token tests."""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Set required env BEFORE importing app
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret-not-real-and-not-short')
os.environ.setdefault('SECRET_KEY', 'test-secret-not-real-and-not-default')
os.environ.setdefault('SIGNED_URL_SECRET', 'test-signed-url-secret')


@pytest.fixture(autouse=True)
def _app_ctx():
    """All sign/verify calls touch current_app — push a context once."""
    from app import app
    with app.app_context():
        yield


def _import_helpers():
    from paper_generation.utils import sign_resource_token, verify_resource_token
    return sign_resource_token, verify_resource_token


def test_round_trip():
    sign, verify = _import_helpers()
    tok = sign("image:paper-abc", "img.png", user_id=42, ttl_seconds=600)
    assert verify(tok, "image:paper-abc", "img.png") == 42


def test_wrong_scope_rejected():
    sign, verify = _import_helpers()
    tok = sign("image:paper-abc", "img.png", user_id=42, ttl_seconds=600)
    assert verify(tok, "file:paper-abc", "img.png") is None


def test_wrong_resource_id_rejected():
    sign, verify = _import_helpers()
    tok = sign("image:paper-abc", "img.png", user_id=42, ttl_seconds=600)
    assert verify(tok, "image:paper-abc", "OTHER.png") is None


def test_expired_rejected():
    sign, verify = _import_helpers()
    tok = sign("image:paper-abc", "img.png", user_id=42, ttl_seconds=60)
    # Forge expiry to be 100s in the past
    expiry, uid, digest = tok.split(".", 2)
    expired_tok = f"{int(time.time()) - 100}.{uid}.{digest}"
    assert verify(expired_tok, "image:paper-abc", "img.png") is None


def test_garbage_token_rejected():
    _, verify = _import_helpers()
    assert verify("not-a-valid-token", "image:paper-abc", "img.png") is None
    assert verify("", "image:paper-abc", "img.png") is None
    assert verify(None, "image:paper-abc", "img.png") is None


def test_tampered_digest_rejected():
    sign, verify = _import_helpers()
    tok = sign("image:paper-abc", "img.png", user_id=42, ttl_seconds=600)
    expiry, uid, digest = tok.split(".", 2)
    tampered = f"{expiry}.{uid}.{'0' * 64}"
    assert verify(tampered, "image:paper-abc", "img.png") is None
