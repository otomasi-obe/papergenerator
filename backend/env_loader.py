"""Centralised .env loader with a test-safety guard.

Why this exists
---------------
Several modules historically called ``load_dotenv(..., override=True)`` at
import time. That is fine in production but DANGEROUS under tests:
``backend/tests/conftest.py`` sets ``DATABASE_URL=sqlite:///:memory:`` BEFORE
importing the app, then ``load_dotenv(override=True)`` clobbers the value with
the production Postgres URL from ``.env``. Any test fixture that calls
``db.drop_all()`` then drops the live database. This actually happened.

This helper performs the same two-file load (project root .env, backend .env
override) but DROPS the override flag whenever a test environment is detected.
It is the single import that all generator/upload modules should call.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv as _load_dotenv


def _running_under_test() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    if os.environ.get("FLASK_ENV") == "testing":
        return True
    db = os.environ.get("DATABASE_URL", "")
    if db.startswith("sqlite:"):
        return True
    return False


def safe_load_dotenv(*paths: Path | str, force_override: bool | None = None) -> None:
    """Load each .env in order. Override behaviour is automatic:

    - Production / dev: later files override earlier files (matches old behaviour).
    - Tests: NEVER override values that the test harness already set.

    Pass ``force_override`` to bypass the auto-detect (rarely needed).
    """
    in_test = _running_under_test()
    for i, p in enumerate(paths):
        is_first = i == 0
        if force_override is not None:
            override = force_override
        elif in_test:
            override = False
        else:
            # Match historical behaviour: first file is base, rest override.
            override = not is_first
        _load_dotenv(p, override=override)


def load_app_env() -> None:
    """The two-file convention used by every generator module."""
    here = Path(__file__).resolve().parent
    safe_load_dotenv(here.parent / ".env", here / ".env")
