"""Chat model is hard-coded to V-DEEPSEEK; client-supplied model must be ignored."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-real-and-not-short")
os.environ.setdefault("SECRET_KEY", "test-secret-not-real-and-not-default")


def test_chat_model_constant_is_v_deepseek():
    import tools.chat as chat

    assert chat.CHAT_MODEL == "V-DEEPSEEK"


def test_call_upstream_default_kwarg_is_v_deepseek():
    """`_call_upstream(model=...)` defaults to V-DEEPSEEK."""
    import inspect

    import tools.chat as chat

    sig = inspect.signature(chat._call_upstream)
    assert sig.parameters["model"].default == "V-DEEPSEEK"


def test_legacy_picker_attrs_removed():
    """The old SELECTABLE_MODELS / DEFAULT_MODEL_KEY / _resolve_model API is gone."""
    import tools.chat as chat

    assert not hasattr(chat, "SELECTABLE_MODELS")
    assert not hasattr(chat, "DEFAULT_MODEL_KEY")
    assert not hasattr(chat, "_resolve_model")


def test_send_message_ignores_client_model_field():
    """Client `model` field on the body must NOT cause a 400 — it's silently dropped.
    We inspect source rather than firing a request to avoid spinning up app+db."""
    import inspect

    import tools.chat as chat

    src = inspect.getsource(chat.send_message)
    # No 400 path mentioning "Unknown model" anymore.
    assert "Unknown model" not in src
    # No reference to the removed picker attrs.
    assert "SELECTABLE_MODELS" not in src
    assert "_resolve_model" not in src
    assert "upstream_model" not in src
