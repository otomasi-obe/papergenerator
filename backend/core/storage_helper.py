"""
Storage Helper for User/Paper-based File Organization
======================================================
Provides path resolution and file operations for the new storage structure:
    backend/data/<username>/<paper_id>/
        chat/
            DDMMYY-HHMMSS-send.json
            DDMMYY-HHMMSS-recv.json
        image/
            <generated images>
        <paper_title>.json         # Editor JSON
        <paper_title>-SLR.json     # SLR JSON
        <paper_title>.docx         # DOCX output

IMPORTANT: Does NOT modify SQL database schema - only changes file storage paths.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Base data directory
DATA_ROOT = Path(__file__).parent / "data"

# Safe filename regex
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_path_seg(value: object, fallback: str = "unknown") -> str:
    """Convert any value to a safe filesystem path segment."""
    s = _SAFE_NAME_RE.sub("_", str(value or "")).strip("._-")
    return s or fallback


def _get_username_from_user_id(user_id) -> str:
    """Map user_id to username. Falls back to user_id if User model not available."""
    try:
        from database.models import User

        uid = int(user_id)
        user = User.query.get(uid)
        if user and user.email:
            local = user.email.split("@", 1)[0]
            return _safe_path_seg(local, f"user_{uid}")
        return f"user_{uid}"
    except Exception:
        return _safe_path_seg(user_id, "anonymous")


def get_user_paper_path(username: str, paper_id: str) -> Path:
    """
    Get base path for a user's paper.

    Args:
        username: Username or user_id (will be sanitized)
        paper_id: Paper ID

    Returns:
        Path: backend/data/<username>/<paper_id>/
    """
    safe_user = _safe_path_seg(username, "anonymous")
    safe_paper = _safe_path_seg(paper_id, "no_paper")
    path = DATA_ROOT / safe_user / safe_paper
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_chat_log(username: str, paper_id: str, direction: str, data: dict) -> Optional[Path]:
    """
    Save chat log with timestamp format DDMMYY-HHMMSS-{direction}.json

    Args:
        username: Username or user_id
        paper_id: Paper ID
        direction: 'send' or 'recv'
        data: Dictionary to save as JSON

    Returns:
        Path to saved file, or None on error
    """
    try:
        base_path = get_user_paper_path(username, paper_id)
        chat_dir = base_path / "chat"
        chat_dir.mkdir(exist_ok=True)

        # Format: DDMMYY-HHMMSS (e.g., 250523-124830)
        timestamp = datetime.now().strftime("%d%m%y-%H%M%S")
        filename = f"{timestamp}-{direction}.json"
        filepath = chat_dir / filename

        # Add metadata
        payload = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "direction": direction,
            **data,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        return filepath
    except Exception as e:
        log.warning("save_chat_log failed: %s", e)
        return None


def get_image_path(username: str, paper_id: str, filename: str) -> Path:
    """
    Get path for an image file.

    Args:
        username: Username or user_id
        paper_id: Paper ID
        filename: Image filename

    Returns:
        Path: backend/data/<username>/<paper_id>/image/<filename>
    """
    base_path = get_user_paper_path(username, paper_id)
    image_dir = base_path / "image"
    image_dir.mkdir(exist_ok=True)
    return image_dir / filename


def get_paper_json_path(username: str, paper_id: str, title: str) -> Path:
    """
    Get path for paper editor JSON.

    Args:
        username: Username or user_id
        paper_id: Paper ID
        title: Paper title (will be sanitized)

    Returns:
        Path: backend/data/<username>/<paper_id>/<title>.json
    """
    base_path = get_user_paper_path(username, paper_id)
    safe_title = _safe_path_seg(title, "untitled")
    return base_path / f"{safe_title}.json"


def get_slr_json_path(username: str, paper_id: str, title: str) -> Path:
    """
    Get path for SLR JSON.

    Args:
        username: Username or user_id
        paper_id: Paper ID
        title: Paper title (will be sanitized)

    Returns:
        Path: backend/data/<username>/<paper_id>/<title>-SLR.json
    """
    base_path = get_user_paper_path(username, paper_id)
    safe_title = _safe_path_seg(title, "untitled")
    return base_path / f"{safe_title}-SLR.json"


def get_docx_path(username: str, paper_id: str, title: str, journal: str = "") -> Path:
    """
    Get path for DOCX output.

    Args:
        username: Username or user_id
        paper_id: Paper ID
        title: Paper title (will be sanitized)
        journal: Optional journal name to prepend

    Returns:
        Path: backend/data/<username>/<paper_id>/<title>.docx
              or backend/data/<username>/<paper_id>/<journal>_<title>.docx
    """
    base_path = get_user_paper_path(username, paper_id)
    safe_title = _safe_path_seg(title, "untitled")

    if journal:
        safe_journal = _safe_path_seg(journal, "")
        filename = f"{safe_journal}_{safe_title}.docx" if safe_journal else f"{safe_title}.docx"
    else:
        filename = f"{safe_title}.docx"

    return base_path / filename


def get_generation_log_path(username: str, paper_id: str, job_id: str) -> Path:
    """
    Get path for paper generation logs.

    Args:
        username: Username or user_id
        paper_id: Paper ID
        job_id: Generation job ID

    Returns:
        Path: backend/data/<username>/<paper_id>/generation/<job_id>/
    """
    base_path = get_user_paper_path(username, paper_id)
    gen_dir = base_path / "generation" / _safe_path_seg(job_id, "no_job")
    gen_dir.mkdir(parents=True, exist_ok=True)
    return gen_dir


def get_legacy_paper_dir(paper_id: str) -> Path:
    """
    Get legacy upload directory for backward compatibility.

    Args:
        paper_id: Paper ID

    Returns:
        Path: backend/data/uploads/<paper_id>/
    """
    return DATA_ROOT / "uploads" / paper_id


def migrate_to_new_structure(user_id: int, paper_id: str) -> bool:
    """
    Migrate files from legacy structure to new structure.
    This is optional and can be called on-demand.

    Args:
        user_id: User ID
        paper_id: Paper ID

    Returns:
        bool: True if migration successful or not needed, False on error
    """
    try:
        import shutil

        username = _get_username_from_user_id(user_id)
        legacy_dir = get_legacy_paper_dir(paper_id)

        if not legacy_dir.exists():
            return True

        new_base = get_user_paper_path(username, paper_id)

        # Migrate images
        for img_file in legacy_dir.glob("*"):
            if img_file.is_file() and img_file.suffix.lower() in {
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".webp",
            }:
                dest = get_image_path(username, paper_id, img_file.name)
                if not dest.exists():
                    shutil.copy2(img_file, dest)

        # Migrate files subdirectory
        legacy_files = legacy_dir / "files"
        if legacy_files.exists():
            new_files = new_base / "files"
            new_files.mkdir(exist_ok=True)
            for file in legacy_files.glob("*"):
                if file.is_file():
                    dest = new_files / file.name
                    if not dest.exists():
                        shutil.copy2(file, dest)

        log.info("Migrated files for paper %s to new structure", paper_id)
        return True
    except Exception as e:
        log.error("Migration failed for paper %s: %s", paper_id, e)
        return False
