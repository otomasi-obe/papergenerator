"""Unit tests for chat streaming components (chat_routes / chat_streaming / chat_scrubber).

Covers _sse, _scrub_control_tokens, _StreamScrubber, _safe_path_seg,
_user_dir_slug, _gen_id, _find_tool_by_name, _select_tools, _build_messages,
_resolve_mode, _set_mode, _MEMORY_RECALL_RE, _LEAKED_TOKENS.
"""

from __future__ import annotations

import json
import os
import re
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("SECRET_KEY", "test-secret")

# Import the module under test
from tools.chat.chat_routes import (
    _gen_id,
    _safe_path_seg,
    _user_dir_slug,
)
from tools.chat.chat_scrubber import _StreamScrubber, _scrub_control_tokens
from tools.chat.chat_streaming import (
    MAX_TOOL_ITERATIONS,
    _MEMORY_RECALL_RE,
    _build_messages,
    _looks_like_start_paper_request,
    _fallback_multi_question_from_text,
    _sse,
    _summary_before_questions,
)
from tools.chat.chat_mode import _find_tool_by_name
from tools.chat.tools import CHAT_TOOLS


# ── _sse ────────────────────────────────────────────────────────────────


def test_sse_format():
    result = _sse("text", {"content": "hello"})
    assert result.startswith("event: text\n")
    assert "data: " in result
    assert result.endswith("\n\n")
    assert '"content": "hello"' in result


def test_sse_encodes_json():
    result = _sse("tool_call", {"name": "WebSearch", "arguments": {"query": "test"}})
    assert "WebSearch" in result
    payload = json.loads(result.split("data: ")[1].strip())
    assert payload["name"] == "WebSearch"


def test_sse_unicode():
    result = _sse("text", {"content": "Halo dunia"})
    assert "Halo dunia" in result


def test_fallback_multi_question_from_plain_text_questions():
    text = """Baik, mari kita susun rencana penulisan paper tentang Robot AGV.

Bidang aplikasi:
Industri manufaktur, pergudangan, rumah sakit, atau bidang lainnya?
Jenis AGV:
Mobile robot berbasis jalur magnetik, laser, vision, atau teknologi lain?
Tujuan penelitian:
Review literatur, perancangan hardware/software, optimasi jalur, atau keselamatan?
"""
    payload = _fallback_multi_question_from_text(text)
    assert payload is not None
    assert len(payload["questions"]) == 3
    assert payload["questions"][0]["label"] == "Bidang aplikasi?"
    assert len(payload["questions"][0]["options"]) == 5
    assert payload["questions"][0]["options"][-1] == {"label": "Ceritakan sendiri...", "value": "E"}
    assert _summary_before_questions(text).startswith("Baik, mari")


def test_fallback_multi_question_from_prompt_item_list():
    text = """Tentu! Untuk memulai, beri tahu saya:

Topik atau bidang penelitian Anda.
Tujuan utama paper.
Jenis paper yang diinginkan.
Format atau template yang harus diikuti.
Batasan waktu atau tenggat akhir penulisan.
"""
    payload = _fallback_multi_question_from_text(text)
    assert payload is not None
    assert len(payload["questions"]) == 3
    assert payload["questions"][0]["label"] == "Topik atau bidang penelitian Anda?"
    assert len(payload["questions"][1]["options"]) == 5
    assert payload["questions"][2]["options"][-1]["label"] == "Ceritakan sendiri..."


def test_start_paper_request_detection():
    assert _looks_like_start_paper_request("saya mau buat paper") is True
    assert _looks_like_start_paper_request("Generate paper lengkap") is True
    assert _looks_like_start_paper_request("halo") is False


# ── _scrub_control_tokens ───────────────────────────────────────────────


def test_scrub_deepseek_function_calls():
    cleaned = _scrub_control_tokens("<｜DSML｜function_calls>hello<｜DSML｜function▁calls>")
    assert "hello" in cleaned
    assert "<｜DSML" not in cleaned


def test_scrub_closed_markers():
    cleaned = _scrub_control_tokens("<｜begin▁of▁sentence｜>Hello<｜end▁of▁sentence｜>")
    assert "Hello" in cleaned
    assert "<｜begin" not in cleaned


def test_scrub_ascii_pipe_markers():
    cleaned = _scrub_control_tokens("<|User|>Hello<|Assistant|>")
    assert cleaned == "Hello"


def test_scrub_only_markers():
    cleaned = _scrub_control_tokens("<｜tool▁calls▁begin｜><｜tool▁calls▁end｜>")
    assert cleaned == ""


def test_scrub_empty_text():
    assert _scrub_control_tokens("") == ""
    assert _scrub_control_tokens(None) is None


def test_scrub_keeps_normal_text():
    text = "Penelitian ini membahas tentang machine learning."
    assert _scrub_control_tokens(text) == text


# ── _StreamScrubber ─────────────────────────────────────────────────────


def test_stream_scrubber_feeds_clean_text():
    scrub = _StreamScrubber()
    out = scrub.feed("Hello World")
    assert out == "Hello World"


def test_stream_scrubber_holds_back_partial_marker():
    scrub = _StreamScrubber()
    out = scrub.feed("Hello <｜")
    assert out == "Hello "
    assert scrub._buf == "<｜"


def test_stream_scrubber_completes_marker():
    scrub = _StreamScrubber()
    scrub.feed("Hello <｜DSML｜function_calls")
    out = scrub.flush()
    assert out == "Hello "
    assert scrub._buf == ""


def test_stream_scrubber_flush_returns_buffered():
    scrub = _StreamScrubber()
    scrub.feed("Hello")
    out = scrub.flush()
    assert out == "Hello"


def test_stream_scrubber_split_across_chunks():
    scrub = _StreamScrubber()
    out1 = scrub.feed("Hello <｜DS")
    assert out1 == "Hello "
    out2 = scrub.feed("ML｜function_calls>World")
    assert "World" in out2
    assert "<｜DSML" not in out2
    assert scrub.flush() == ""


def test_stream_scrubber_empty_feed():
    scrub = _StreamScrubber()
    assert scrub.feed("") == ""


# ── _gen_id ─────────────────────────────────────────────────────────────


def test_gen_id_length():
    assert len(_gen_id()) == 16


def test_gen_id_hex():
    assert all(c in "0123456789abcdef" for c in _gen_id())


def test_gen_id_unique():
    ids = {_gen_id() for _ in range(100)}
    assert len(ids) == 100


# ── _safe_path_seg ──────────────────────────────────────────────────────


def test_safe_path_seg_normal():
    assert _safe_path_seg("hello-world", "fallback") == "hello-world"


def test_safe_path_seg_special_chars():
    seg = _safe_path_seg("hello@world!", "fallback")
    assert "@" not in seg
    assert "!" not in seg


def test_safe_path_seg_empty_uses_fallback():
    assert _safe_path_seg("", "fallback") == "fallback"
    assert _safe_path_seg(None, "fallback") == "fallback"


# ── _user_dir_slug ──────────────────────────────────────────────────────


@patch("tools.chat.chat_routes.User")
def test_user_dir_slug_findable(mock_user):
    mock_user_obj = MagicMock()
    mock_user_obj.email = "user@test.com"
    mock_user.query.get.return_value = mock_user_obj
    slug = _user_dir_slug("42")
    assert "42" in slug
    assert "user" in slug


@patch("tools.chat.chat_routes.User")
def test_user_dir_slug_no_email(mock_user):
    mock_user_obj = MagicMock()
    mock_user_obj.email = None
    mock_user.query.get.return_value = mock_user_obj
    slug = _user_dir_slug("42")
    assert slug == "42"


@patch("tools.chat.chat_routes.User")
def test_user_dir_slug_not_found(mock_user):
    mock_user.query.get.return_value = None
    slug = _user_dir_slug("42")
    assert slug == "42"


def test_user_dir_slug_non_int():
    slug = _user_dir_slug("anon-user")
    assert "anon" in slug


# ── _find_tool_by_name ──────────────────────────────────────────────────


def test_find_tool_by_name_finds_existing():
    for tool_dict in CHAT_TOOLS:
        name = tool_dict.get("name") or tool_dict.get("function", {}).get("name", "")
        if name:
            found = _find_tool_by_name(name)
            assert found is not None
            break


def test_find_tool_by_name_returns_none():
    assert _find_tool_by_name("BogusTool") is None
    assert _find_tool_by_name("") is None
    assert _find_tool_by_name(None) is None


def test_find_tool_by_name_web_search():
    found = _find_tool_by_name("WebSearch")
    assert found is not None
    name = found.get("name") or found.get("function", {}).get("name", "")
    assert name == "WebSearch"


# ── _MEMORY_RECALL_RE ───────────────────────────────────────────────────


def test_memory_recall_re_matches_ingatan():
    assert _MEMORY_RECALL_RE.search("apa yang kamu ingat?")


def test_memory_recall_re_matches_memory():
    assert _MEMORY_RECALL_RE.search("show me my memory")


def test_memory_recall_re_matches_apa_kamu_tau():
    assert _MEMORY_RECALL_RE.search("apa kamu tau tentang saya?")


def test_memory_recall_re_no_match():
    assert not _MEMORY_RECALL_RE.search("tolong buatkan abstrak")


# ── MAX_TOOL_ITERATIONS ─────────────────────────────────────────────────


def test_max_tool_iterations():
    assert MAX_TOOL_ITERATIONS == 10
