"""Unit tests for chat tool executor (tools.py).

Covers _dispatch_tool, execute_tool, _propose, _propose_revisi,
_safe_user_error, and all individual tool handlers.
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pathlib
from tools.chat.chat_streaming import _list_available_journals
from tools.chat.tools import (
    PROPOSAL_PREFIX,
    _dispatch_tool,
    _format_literature_block,
    _format_memory_block,
    _get_memory_value,
    _list_attached_files,
    _propose,
    _propose_revisi,
    _read_attached_file,
    _safe_user_error,
    _to_roman,
    _walk_content_for_numbering,
    execute_tool,
)

# ── _propose / PROPOSAL_PREFIX ──────────────────────────────────────────


def test_propose_wraps_json_with_prefix():
    result = _propose("test_kind", {"key": "value"})
    assert result.startswith(PROPOSAL_PREFIX)
    payload = json.loads(result[len(PROPOSAL_PREFIX) :])
    assert payload["kind"] == "test_kind"
    assert payload["key"] == "value"


def test_propose_revisi_paragraph_scope():
    result = _propose_revisi(
        tool="Paraphrase",
        scope="paragraph",
        section_index=2,
        content_index=1,
        text="original text",
        rewrite="rewritten text",
    )
    assert result.startswith(PROPOSAL_PREFIX)
    p = json.loads(result[len(PROPOSAL_PREFIX) :])
    assert p["kind"] == "propose_revisi"
    assert p["tool"] == "Paraphrase"
    assert p["scope"] == "paragraph"
    assert p["section_index"] == 2
    assert p["content_index"] == 1


def test_propose_revisi_drops_none_fields():
    result = _propose_revisi(
        tool="FixGrammar", scope="section", section_index=None, content_index=None, text="", rewrite="fix"
    )
    p = json.loads(result[len(PROPOSAL_PREFIX) :])
    assert "section_index" not in p
    assert "content_index" not in p


# ── _safe_user_error ────────────────────────────────────────────────────


def test_safe_user_error_hides_sql():
    msg = _safe_user_error("psycopg2 error: relation does not exist")
    assert "psycopg2" not in msg
    assert "internal" in msg or "gangguan" in msg


def test_safe_user_error_hides_traceback():
    msg = _safe_user_error('Traceback File "x.py", line 10, in foo')
    assert "Traceback" not in msg
    assert "internal" in msg or "gangguan" in msg


def test_safe_user_error_api_busy():
    msg = _safe_user_error("API error: 500 upstream timeout")
    assert "sibuk" in msg


def test_safe_user_error_truncates_long():
    msg = _safe_user_error("x" * 300)
    assert len(msg) <= 240 + 1  # 240 + ellipsis char


def test_safe_user_error_fallback_on_none():
    assert _safe_user_error(None) == "Terjadi kendala teknis. Coba kirim lagi sebentar."
    assert _safe_user_error("") == "Terjadi kendala teknis. Coba kirim lagi sebentar."


# ── _dispatch_tool —— RouteIntent ───────────────────────────────────────


def test_route_intent_returns_route_kind():
    result = _dispatch_tool("RouteIntent", {"mode": "edit", "reasoning": "user wants edit"}, user_id=1)
    assert isinstance(result, dict)
    assert result["kind"] == "route"
    assert result["mode"] == "edit"


def test_route_intent_default_mode():
    result = _dispatch_tool("RouteIntent", {}, user_id=1)
    assert result["mode"] == "casual"


# ── _dispatch_tool —— ProposeChips ─────────────────────────────────────


def test_propose_chips_wraps_proposal():
    result = _dispatch_tool("ProposeChips", {"chips": [{"label": "Yes"}], "context_hint": "test"}, user_id=1)
    assert result.startswith(PROPOSAL_PREFIX)
    p = json.loads(result[len(PROPOSAL_PREFIX) :])
    assert p["kind"] == "chips"
    assert p["chips"] == [{"label": "Yes"}]


def test_propose_chips_invalid_chips_defaults_empty():
    result = _dispatch_tool("ProposeChips", {"chips": "not-a-list"}, user_id=1)
    p = json.loads(result[len(PROPOSAL_PREFIX) :])
    assert p["chips"] == []


# ── _dispatch_tool —— Propose* tools ────────────────────────────────────


def test_propose_title():
    r = _dispatch_tool("ProposeTitle", {"title": "My Paper Title"}, user_id=1)
    p = json.loads(r[len(PROPOSAL_PREFIX) :])
    assert p["kind"] == "title"
    assert p["value"] == "My Paper Title"


def test_propose_abstract():
    r = _dispatch_tool("ProposeAbstract", {"abstract": "abstract text"}, user_id=1)
    p = json.loads(r[len(PROPOSAL_PREFIX) :])
    assert p["kind"] == "abstract"


def test_propose_keywords():
    r = _dispatch_tool("ProposeKeywords", {"keywords": ["ML", "AI"]}, user_id=1)
    p = json.loads(r[len(PROPOSAL_PREFIX) :])
    assert p["kind"] == "keywords"
    assert p["value"] == ["ML", "AI"]


def test_propose_section():
    r = _dispatch_tool("ProposeSection", {"section_index": 0, "title": "Intro", "content": "hello"}, user_id=1)
    p = json.loads(r[len(PROPOSAL_PREFIX) :])
    assert p["kind"] == "section"
    assert p["section_index"] == 0


def test_propose_reference():
    r = _dispatch_tool("ProposeReference", {"ref_index": 1, "value": "[1] Ref"}, user_id=1)
    p = json.loads(r[len(PROPOSAL_PREFIX) :])
    assert p["kind"] == "reference"


def test_propose_journal():
    r = _dispatch_tool("ProposeJournal", {"journal": "IEEE"}, user_id=1)
    p = json.loads(r[len(PROPOSAL_PREFIX) :])
    assert p["kind"] == "journal"
    assert p["value"] == "IEEE"


def test_request_export_docx():
    r = _dispatch_tool("RequestExportDocx", {}, user_id=1)
    p = json.loads(r[len(PROPOSAL_PREFIX) :])
    assert p["kind"] == "export_docx"


# ── _dispatch_tool —— Revisi-mode tools ────────────────────────────────


def test_paraphrase_proposal():
    r = _dispatch_tool("Paraphrase", {
        "scope": "paragraph", "section_index": 1, "text": "old", "rewrite": "new"
    }, user_id=1)
    assert r.startswith(PROPOSAL_PREFIX)


def test_fix_grammar_proposal():
    r = _dispatch_tool("FixGrammar", {
        "scope": "section", "section_index": 0, "text": "bad grammar", "rewrite": "good grammar"
    }, user_id=1)
    assert r.startswith(PROPOSAL_PREFIX)


def test_translate_proposal():
    r = _dispatch_tool("Translate", {
        "scope": "whole", "text": "Hello", "rewrite": "Halo", "target_language": "id"
    }, user_id=1)
    p = json.loads(r[len(PROPOSAL_PREFIX) :])
    assert p["kind"] == "propose_revisi"
    assert p["target_language"] == "id"


# ── _dispatch_tool —— SetCitationStyle / SetLanguage ────────────────────


@patch("tools.chat.tool_memory._save_memory")
def test_set_citation_style(mock_save):
    mock_save.return_value = "Saved citation_style."
    r = _dispatch_tool("SetCitationStyle", {"style": "APA"}, paper_id="p1", user_id=1)
    p = json.loads(r[len(PROPOSAL_PREFIX) :])
    assert p["kind"] == "setting_saved"
    assert p["value"] == "APA"


@patch("tools.chat.tool_memory._save_memory")
def test_set_citation_style_invalid_falls_back(mock_save):
    mock_save.return_value = "Saved citation_style."
    r = _dispatch_tool("SetCitationStyle", {"style": "INVALID"}, paper_id="p1", user_id=1)
    p = json.loads(r[len(PROPOSAL_PREFIX) :])
    assert p["value"] == "IEEE"


@patch("tools.chat.tool_memory._save_memory")
def test_set_language(mock_save):
    mock_save.return_value = "Saved paper_language."
    r = _dispatch_tool("SetLanguage", {"language": "en"}, paper_id="p1", user_id=1)
    p = json.loads(r[len(PROPOSAL_PREFIX) :])
    assert p["value"] == "en"


@patch("tools.chat.tool_memory._save_memory")
def test_set_language_invalid_falls_back(mock_save):
    mock_save.return_value = "Saved paper_language."
    r = _dispatch_tool("SetLanguage", {"language": "fr"}, paper_id="p1", user_id=1)
    p = json.loads(r[len(PROPOSAL_PREFIX) :])
    assert p["value"] == "id"


# ── _dispatch_tool —— AskQuestions ──────────────────────────────────────


def test_ask_questions():
    r = _dispatch_tool("AskQuestions", {
        "questions": [
            {"key": "q1", "label": "Question 1", "options": [{"label": "A", "value": "A"}]},
        ]
    }, user_id=1)
    p = json.loads(r[len(PROPOSAL_PREFIX) :])
    assert p["kind"] == "multi_question"
    assert len(p["questions"]) == 1
    assert len(p["questions"][0]["options"]) == 5
    assert p["questions"][0]["options"][-1] == {"label": "Ceritakan sendiri...", "value": "E"}


def test_ask_questions_empty_returns_error():
    r = _dispatch_tool("AskQuestions", {"questions": []}, user_id=1)
    assert r.startswith("Error:")


def test_ask_questions_max_3():
    many = [{"key": f"q{i}", "label": f"Q{i}"} for i in range(10)]
    r = _dispatch_tool("AskQuestions", {"questions": many}, user_id=1)
    p = json.loads(r[len(PROPOSAL_PREFIX) :])
    assert len(p["questions"]) <= 3


# ── _dispatch_tool —— ReviewPaper / ReviseData ─────────────────────────


def test_review_paper():
    r = _dispatch_tool("ReviewPaper", {"directive": "check grammar", "scope": "whole"}, user_id=1)
    p = json.loads(r[len(PROPOSAL_PREFIX) :])
    assert p["kind"] == "review_plan"
    assert p["directive"] == "check grammar"


def test_revise_data():
    r = _dispatch_tool("ReviseData", {"directive": "fix table 1"}, user_id=1)
    p = json.loads(r[len(PROPOSAL_PREFIX) :])
    assert p["kind"] == "revise_data"


# ── _dispatch_tool —— unknown tool ──────────────────────────────────────


def test_unknown_tool():
    r = _dispatch_tool("NonExistentTool", {}, user_id=1)
    assert "Unknown tool" in r
    assert "NonExistentTool" in r


# ── _dispatch_tool —— blocked tools ─────────────────────────────────────


def test_write_is_blocked():
    r = _dispatch_tool("Write", {"file_path": "/tmp/test.txt", "content": "test"}, user_id=1)
    assert "not permitted" in r


def test_edit_is_blocked():
    r = _dispatch_tool("Edit", {"file_path": "/tmp/test.txt", "content": "test"}, user_id=1)
    assert "not permitted" in r


# ── execute_tool (top-level) ────────────────────────────────────────────


@patch("tools.chat.tool_executor._log_chat_call")
def test_execute_tool_logs_call_and_result(mock_log):
    result = execute_tool("RouteIntent", {"mode": "edit"}, user_id=1, paper_id="p1", conv_id="c1")
    assert mock_log.call_count >= 1
    assert isinstance(result, dict)


@patch("tools.chat.tool_executor._log_chat_call")
def test_execute_tool_raises_on_error(mock_log):
    with patch("tools.chat.tool_executor._dispatch_tool", side_effect=ValueError("boom")):
        import pytest
        with pytest.raises(ValueError):
            execute_tool("RouteIntent", {}, user_id=1)


# ── _format_literature_block ────────────────────────────────────────────

@patch("tools.chat.tool_helpers.db.session.query")
def test_format_literature_block_empty(mock_query):
    mock_query.return_value.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
    result = _format_literature_block("p1")
    assert result == ""


# ── _format_memory_block ────────────────────────────────────────────────

@patch("tools.chat.tool_helpers.ProjectMemory")
def test_format_memory_block_empty(mock_pm):
    mock_pm.query.filter_by.return_value.all.return_value = []
    result = _format_memory_block("p1")
    assert result == ""


@patch("tools.chat.tool_helpers.ProjectMemory")
def test_format_memory_block_with_entries(mock_pm):
    class FakeMem:
        key = "jurusan"
        value = "Teknik Informatika"

    mock_pm.query.filter_by.return_value.all.return_value = [FakeMem()]
    result = _format_memory_block("p1")
    assert "Jurusan" in result
    assert "Teknik Informatika" in result


# ── _to_roman ────────────────────────────────────────────────────────────


def test_to_roman():
    assert _to_roman(1) == "I"
    assert _to_roman(4) == "IV"
    assert _to_roman(9) == "IX"
    assert _to_roman(10) == "X"
    assert _to_roman(49) == "XLIX"
    assert _to_roman(100) == "C"


# ── _walk_content_for_numbering ─────────────────────────────────────────


def test_walk_content_for_numbering():
    content = [
        {"id": "gambar", "url": "fig1.png"},
        {"id": "tabel", "caption": "Table 1"},
        {"id": "rumus", "latex": "E=mc^2"},
    ]
    figs, tbls, eqs = [], [], []
    _walk_content_for_numbering(content, 1, 1, 1, figs, tbls, eqs, "Intro")
    assert len(figs) == 1
    assert figs[0]["fig_number"] == 1
    assert len(tbls) == 1
    assert tbls[0]["table_number"] == 1
    assert len(eqs) == 1
    assert eqs[0]["eq_number"] == 1


# ── _list_available_journals ────────────────────────────────────────────


@patch.object(pathlib.Path, "glob")
def test_list_available_journals(mock_glob):
    mock_glob.return_value = []
    result = _list_available_journals()
    assert isinstance(result, list)
