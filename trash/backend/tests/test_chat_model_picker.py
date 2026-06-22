"""Chat model is server-controlled via the per-index endpoint chain
(MODELCHAT1..3); the client-supplied `model` field must be ignored.

The legacy hard-coded V-DEEPSEEK constant + _call_upstream picker were removed
when chat was migrated to the per-index failover chain (route_chat_call).
These tests assert the *current* contract: server picks the model, the client
cannot override it, and the old picker API is gone.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-real-and-not-short")
os.environ.setdefault("SECRET_KEY", "test-secret-not-real-and-not-default")


def test_chat_uses_per_index_chain():
    """Chat resolves its model from the MODELCHAT1..3 env chain, not a
    hard-coded constant."""
    from utils.ai_tools.model_config import get_chat_model_chain, get_primary_chat_model

    models = get_chat_model_chain()
    assert isinstance(models, list)
    # Primary chat model is whatever sits at the head of the chain.
    primary = get_primary_chat_model()
    assert isinstance(primary, str) and primary


def test_send_message_routes_via_chat_chain():
    """`send_message` drives the AI through route_chat_call (per-index chain),
    not a single hard-coded upstream."""
    import inspect

    import tools.chat.chat as chat

    src = inspect.getsource(chat.send_message)
    assert "route_chat_call" in src, "send_message should use the per-index chat chain"


def test_legacy_picker_attrs_removed():
    """The old SELECTABLE_MODELS / DEFAULT_MODEL_KEY / _resolve_model /
    CHAT_MODEL / _call_upstream picker API is gone."""
    import tools.chat as chat
    import tools.chat.chat as chat_mod

    for mod in (chat, chat_mod):
        assert not hasattr(mod, "SELECTABLE_MODELS")
        assert not hasattr(mod, "DEFAULT_MODEL_KEY")
        assert not hasattr(mod, "_resolve_model")
        assert not hasattr(mod, "CHAT_MODEL")
        assert not hasattr(mod, "_call_upstream")


def test_send_message_ignores_client_model_field():
    """Client `model` field on the body must NOT cause a 400 and must NOT be
    forwarded — the server controls model selection. We inspect source rather
    than firing a request to avoid spinning up app+db."""
    import inspect

    import tools.chat.chat as chat

    src = inspect.getsource(chat.send_message)
    # No 400 path mentioning "Unknown model" anymore.
    assert "Unknown model" not in src
    # Client model field is not read off the request body.
    assert "data.get('model'" not in src
    assert 'data.get("model"' not in src
    assert 'data["model"]' not in src
    # No reference to the removed picker attrs.
    assert "SELECTABLE_MODELS" not in src
    assert "_resolve_model" not in src
