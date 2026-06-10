"""Google OAuth state signing tests."""

import os
import sys
from importlib import import_module

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

auth_module = import_module("utils.auth_bp.auth")


def test_signed_state_verifies_when_hmac_contains_dot(app, monkeypatch):
    digest = b"abc.def" + b"x" * 25

    class FakeHmac:
        def hexdigest(self):
            return digest.hex()

    monkeypatch.setattr(auth_module.secrets, "token_urlsafe", lambda _: "oauth-state")
    monkeypatch.setattr(auth_module.hmac, "new", lambda *args, **kwargs: FakeHmac())

    with app.app_context():
        signed_state = auth_module._make_signed_state()

    assert auth_module._verify_signed_state(signed_state) == "oauth-state"
