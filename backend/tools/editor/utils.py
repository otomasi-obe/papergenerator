"""
Shared helpers used by papers/files/images blueprints.
Extracted to break circular imports between blueprints.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from pathlib import Path

from flask import current_app

PAPER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def upload_folder() -> Path:
    return Path(current_app.root_path) / "data/uploads"


def safe_paper_dir(paper_id: str) -> Path | None:
    """Return paper directory under user storage: user/<username>/<paper_id>/.

    Falls back to legacy data/uploads/<paper_id>/ if paper/user not found.
    """
    if not paper_id or not PAPER_ID_RE.match(paper_id):
        return None

    # Primary: user/<username>/<paper_id>/
    try:
        from database.models import Paper, User
        paper = Paper.query.filter_by(id=paper_id).first()
        if paper:
            user = User.query.get(paper.user_id)
            if user and user.email:
                import re as _re
                username = _re.sub(r'[^A-Za-z0-9._-]+', '_', user.email.split("@")[0]).strip("._-") or "unknown"
                user_dir = (Path(current_app.root_path) / "user" / username / paper_id).resolve()
                base = (Path(current_app.root_path) / "user").resolve()
                try:
                    user_dir.relative_to(base)
                except ValueError:
                    return None
                return user_dir
    except Exception:
        pass

    # Fallback: legacy data/uploads/<paper_id>/
    base = upload_folder().resolve()
    target = (upload_folder() / paper_id).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return None
    return target


def is_image_bytes(head: bytes, ext: str) -> bool:
    """Magic-byte sniff so a renamed .exe doesn't pass as .png."""
    if not head:
        return False
    if ext == ".png" and head.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if ext in (".jpg", ".jpeg") and head.startswith(b"\xff\xd8\xff"):
        return True
    if ext == ".gif" and (head.startswith(b"GIF87a") or head.startswith(b"GIF89a")):
        return True
    if ext == ".bmp" and head.startswith(b"BM"):
        return True
    if ext == ".webp" and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return True
    return False


def sign_resource_token(scope: str, resource_id: str, user_id: int, ttl_seconds: int = 600) -> str:
    """HMAC-signed, scoped, short-lived token for asset URLs (image/file)."""
    expiry = int(time.time()) + max(60, int(ttl_seconds))
    msg = f"{scope}|{resource_id}|{user_id}|{expiry}".encode()
    digest = hmac.new(
        current_app.config["SIGNED_URL_SECRET"].encode(),
        msg,
        hashlib.sha256,
    ).hexdigest()
    return f"{expiry}.{user_id}.{digest}"


def verify_resource_token(token: str, scope: str, resource_id: str) -> int | None:
    """Return user_id if token is valid for (scope, resource_id), else None."""
    try:
        expiry_str, uid_str, digest = token.split(".", 2)
        expiry = int(expiry_str)
        uid = int(uid_str)
    except (ValueError, AttributeError):
        return None
    if expiry < int(time.time()):
        return None
    msg = f"{scope}|{resource_id}|{uid}|{expiry}".encode()
    expected = hmac.new(
        current_app.config["SIGNED_URL_SECRET"].encode(),
        msg,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, digest):
        return None
    return uid
