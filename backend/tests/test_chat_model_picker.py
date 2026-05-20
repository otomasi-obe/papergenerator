"""Model selector tests for chat blueprint."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret-not-real-and-not-short')
os.environ.setdefault('SECRET_KEY', 'test-secret-not-real-and-not-default')


def _import():
    from chat import _resolve_model, SELECTABLE_MODELS, DEFAULT_MODEL_KEY
    return _resolve_model, SELECTABLE_MODELS, DEFAULT_MODEL_KEY


def test_known_keys_map_through():
    resolve, allow, _ = _import()
    for key in allow.keys():
        assert resolve(key) == allow[key]


def test_unknown_key_returns_none():
    resolve, _, _ = _import()
    assert resolve("V-FAKE") is None
    assert resolve("anthropic-secret-name") is None
    assert resolve("../../etc/passwd") is None


def test_empty_falls_back_to_default():
    resolve, allow, default_key = _import()
    # MODEL env unset → falls back to default key value
    result = resolve("")
    # Result must be either the env MODEL (if set) or the default mapped value
    assert result in (allow[default_key], os.environ.get('AIOTOMASI_MODEL') or allow[default_key])


def test_none_falls_back_to_default():
    resolve, allow, default_key = _import()
    result = resolve(None)
    assert result in (allow[default_key], os.environ.get('AIOTOMASI_MODEL') or allow[default_key])
