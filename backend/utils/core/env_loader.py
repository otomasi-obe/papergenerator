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


def normalize_aiotomasi_aliases() -> None:
    """Bridge numbered provider slots → base names.

    The canonical ``.env`` declares provider slots
    (``AIOTOMASI_API1/2/3``, ``AIOTOMASI_APIKEY1/2/3``) but every call site
    reads the BASE names (``AIOTOMASI_API`` / ``AIOTOMASI_APIKEY``). When the
    base name is unset, fall back to the first available slot so the upstream
    gateway URL/key resolve. Idempotent; never clobbers an explicitly-set base value.
    """
    for base, slot in (
        ("AIOTOMASI_API", "AIOTOMASI_API1"),
        ("AIOTOMASI_APIKEY", "AIOTOMASI_APIKEY1"),
    ):
        if not os.getenv(base) and os.getenv(slot):
            os.environ[base] = os.environ[slot]
    
    # Also bridge slot 2 or 3 if slot 1 is missing
    if not os.getenv("AIOTOMASI_API"):
        for i in (2, 3):
            if os.getenv(f"AIOTOMASI_API{i}"):
                os.environ["AIOTOMASI_API"] = os.environ[f"AIOTOMASI_API{i}"]
                break
    if not os.getenv("AIOTOMASI_APIKEY"):
        for i in (2, 3):
            if os.getenv(f"AIOTOMASI_APIKEY{i}"):
                os.environ["AIOTOMASI_APIKEY"] = os.environ[f"AIOTOMASI_APIKEY{i}"]
                break


def load_app_env() -> None:
    """The two-file convention used by every generator module.

    Loads project-root ``.env`` then ``backend/.env`` (override), then bridges
    the numbered AIOTOMASI provider slots onto the base names the code reads.
    """
    here = Path(__file__).resolve().parent          # backend/utils/core
    backend_dir = here.parent.parent                # backend
    project_root = backend_dir.parent               # repo root
    safe_load_dotenv(project_root / ".env", backend_dir / ".env")
    normalize_aiotomasi_aliases()
