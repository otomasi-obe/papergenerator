"""
Unit tests for core/storage_helper.py — File storage path management.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

os.environ.setdefault("FLASK_ENV", "testing")

try:
    from core import storage_helper
    from core.storage_helper import (
        _safe_path_seg,
        get_docx_path,
        get_generation_log_path,
        get_image_path,
        get_legacy_paper_dir,
        get_paper_json_path,
        get_slr_json_path,
        get_user_paper_path,
        save_chat_log,
    )
except Exception as e:
    pytest.skip(f"Storage helper module bootstrap failed: {e}", allow_module_level=True)


@pytest.fixture()
def temp_data_root(tmp_path):
    original_root = storage_helper.DATA_ROOT
    storage_helper.DATA_ROOT = tmp_path
    yield tmp_path
    storage_helper.DATA_ROOT = original_root


def test_safe_path_seg_basic():
    assert _safe_path_seg("hello") == "hello"
    assert _safe_path_seg("hello_world") == "hello_world"
    assert _safe_path_seg("hello-world") == "hello-world"
    assert _safe_path_seg("hello.world") == "hello.world"


def test_safe_path_seg_special_chars():
    assert _safe_path_seg("hello world") == "hello_world"
    assert _safe_path_seg("hello/world") == "hello_world"
    assert _safe_path_seg("hello\\world") == "hello_world"
    assert _safe_path_seg("hello@world") == "hello_world"


def test_safe_path_seg_empty():
    assert _safe_path_seg("") == "unknown"
    assert _safe_path_seg(None) == "unknown"
    assert _safe_path_seg("", fallback="custom") == "custom"


def test_safe_path_seg_strip():
    assert _safe_path_seg("...hello...") == "hello"
    assert _safe_path_seg("___hello___") == "hello"
    assert _safe_path_seg("---hello---") == "hello"


def test_get_user_paper_path(temp_data_root):
    path = get_user_paper_path("alice", "paper123")

    assert path.exists()
    assert path.is_dir()
    assert "alice" in str(path)
    assert "paper123" in str(path)


def test_get_user_paper_path_sanitization(temp_data_root):
    path = get_user_paper_path("alice@example.com", "paper-123")

    assert path.exists()
    assert "@" not in str(path)


def test_save_chat_log(temp_data_root):
    data = {"message": "Hello", "role": "user"}
    filepath = save_chat_log("alice", "paper123", "send", data)

    assert filepath is not None
    assert filepath.exists()
    assert filepath.suffix == ".json"
    assert "send" in filepath.name

    import json
    with open(filepath, "r") as f:
        saved_data = json.load(f)

    assert saved_data["message"] == "Hello"
    assert saved_data["role"] == "user"
    assert saved_data["direction"] == "send"
    assert "ts" in saved_data


def test_save_chat_log_creates_directory(temp_data_root):
    filepath = save_chat_log("bob", "paper456", "recv", {"content": "Response"})

    assert filepath is not None
    assert filepath.parent.name == "chat"
    assert filepath.parent.exists()


def test_get_image_path(temp_data_root):
    path = get_image_path("alice", "paper123", "image1.png")

    assert path.parent.name == "image"
    assert path.parent.exists()
    assert path.name == "image1.png"


def test_get_paper_json_path(temp_data_root):
    path = get_paper_json_path("alice", "paper123", "My Research Paper")

    assert path.suffix == ".json"
    assert "My_Research_Paper" in path.name or "My" in path.name


def test_get_slr_json_path(temp_data_root):
    path = get_slr_json_path("alice", "paper123", "Literature Review")

    assert path.suffix == ".json"
    assert "SLR" in path.name


def test_get_docx_path_basic(temp_data_root):
    path = get_docx_path("alice", "paper123", "My Paper")

    assert path.suffix == ".docx"
    assert "My_Paper" in path.name or "My" in path.name


def test_get_docx_path_with_journal(temp_data_root):
    path = get_docx_path("alice", "paper123", "My Paper", journal="IEEE")

    assert path.suffix == ".docx"
    assert "IEEE" in path.name


def test_get_generation_log_path(temp_data_root):
    path = get_generation_log_path("alice", "paper123", "job456")

    assert path.exists()
    assert path.is_dir()
    assert "generation" in str(path)
    assert "job456" in str(path)


def test_get_legacy_paper_dir(temp_data_root):
    path = get_legacy_paper_dir("paper123")

    assert "uploads" in str(path)
    assert "paper123" in str(path)


def test_multiple_users_same_paper_id(temp_data_root):
    path1 = get_user_paper_path("alice", "paper1")
    path2 = get_user_paper_path("bob", "paper1")

    assert path1 != path2
    assert path1.exists()
    assert path2.exists()


def test_path_creation_idempotent(temp_data_root):
    path1 = get_user_paper_path("alice", "paper123")
    path2 = get_user_paper_path("alice", "paper123")

    assert path1 == path2
    assert path1.exists()


def test_special_characters_in_title(temp_data_root):
    path = get_paper_json_path("alice", "paper123", "Paper: A Study (2024)")

    assert path.exists() or path.parent.exists()
    assert ":" not in path.name
    assert "(" not in path.name
    assert ")" not in path.name


def test_unicode_in_username(temp_data_root):
    path = get_user_paper_path("用户", "paper123")

    assert path.exists()
    assert path.is_dir()


def test_very_long_title(temp_data_root):
    long_title = "A" * 300
    path = get_paper_json_path("alice", "paper123", long_title)

    assert path.parent.exists()
    assert len(path.name) < 300
