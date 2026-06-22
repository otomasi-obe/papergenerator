"""Unit tests for workflow engine (engine.py) and tool integration (tool.py).

Covers WORKFLOW_PHASES, get_offline_onboarding_questions, get_phase_questions,
_generate_phase2_suggestions, _extract_json_array, generate_ai_options, 
validate_workflow, resolve_static_label, _snapshot_options, start_workflow,
save_workflow_answers.
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

import pytest  # noqa: E402

pytest.importorskip(
    "tools.chat.engine",
    reason="chat architecture consolidated into tools/chat/chat.py; "
    "legacy modular engine module removed. Test pending rewrite "
    "against the new chat.py API.",
)
from tools.chat.engine import (
    FIRST_DYNAMIC_PHASE,
    ONBOARDING_QUESTION_IDS,
    ONBOARDING_RECOMMENDED,
    STATIC_OPTION_KEYS,
    WORKFLOW_PHASES,
    _append_free_text,
    _extract_json_array,
    _get_fallback_options,
    clear_ai_options_cache,
    generate_ai_options,
    get_offline_onboarding_questions,
    get_phase_questions,
    resolve_static_label,
    validate_workflow,
)


# ── WORKFLOW_PHASES shape ──────────────────────────────────────────────


def test_workflow_has_all_phases():
    for i in range(10):
        assert str(i) in WORKFLOW_PHASES


def test_workflow_phase_names():
    assert WORKFLOW_PHASES["0"]["name"] == "Pre-Questionnaire — Status Awal"
    assert WORKFLOW_PHASES["1"]["name"] == "Profil Dasar Paper"
    assert WORKFLOW_PHASES["9"]["name"] == "Validasi & Finalisasi"


def test_phase_9_has_no_questions():
    assert WORKFLOW_PHASES["9"]["questions"] == []


def test_phase_6_has_branches():
    assert "branches" in WORKFLOW_PHASES["6"]
    assert "quantitative" in WORKFLOW_PHASES["6"]["branches"]
    assert "qualitative" in WORKFLOW_PHASES["6"]["branches"]
    assert "literature" in WORKFLOW_PHASES["6"]["branches"]


# ── ONBOARDING_QUESTION_IDS / RECOMMENDED ──────────────────────────────


def test_onboarding_question_ids():
    assert "0.1" in ONBOARDING_QUESTION_IDS
    assert "0.2" in ONBOARDING_QUESTION_IDS
    assert "1.3" in ONBOARDING_QUESTION_IDS
    assert len(ONBOARDING_QUESTION_IDS) == 6


def test_onboarding_recommended():
    assert ONBOARDING_RECOMMENDED["0.1"] == "A"
    assert ONBOARDING_RECOMMENDED["1.3"] == "B"


def test_first_dynamic_phase():
    assert FIRST_DYNAMIC_PHASE == "1"


# ── STATIC_OPTION_KEYS ─────────────────────────────────────────────────


def test_static_option_keys_contains_field():
    assert "field" in STATIC_OPTION_KEYS


def test_static_option_keys_excludes_ai_generated():
    assert "topik" not in STATIC_OPTION_KEYS
    assert "title" not in STATIC_OPTION_KEYS


# ── _append_free_text ─────────────────────────────────────────────────


def test_append_free_text_appends_e():
    opts = [{"label": "A", "value": "A"}, {"label": "B", "value": "B"}]
    result = _append_free_text(opts)
    assert len(result) == 3
    assert result[2]["label"] == "Ceritakan sendiri..."
    assert result[2]["value"] == "E"


def test_append_free_text_picks_next_letter():
    opts = [{"label": x, "value": x} for x in "ABCDE"]
    result = _append_free_text(opts)
    assert result[-1]["value"] == "F"


# ── get_offline_onboarding_questions ───────────────────────────────────


def test_get_offline_onboarding_returns_list():
    questions = get_offline_onboarding_questions()
    assert len(questions) == len(ONBOARDING_QUESTION_IDS)
    assert all("key" in q for q in questions)


def test_offline_questions_have_recommended_defaults():
    questions = get_offline_onboarding_questions()
    for q in questions:
        has_recommended = any(
            opt.get("recommended") for opt in (q.get("options") or [])
        )
        if q.get("id") in ONBOARDING_RECOMMENDED:
            assert has_recommended, f"{q['id']} should have recommended"
        else:
            assert not has_recommended


# ── resolve_static_label ───────────────────────────────────────────────


def test_resolve_static_label_finds_label():
    label = resolve_static_label("field", "A")
    assert label == "Ilmu Komputer & IT"


def test_resolve_static_label_custom_value():
    label = resolve_static_label("field", "custom value")
    assert label == "custom value"


def test_resolve_static_label_ai_generated():
    label = resolve_static_label("topik", "AI")
    assert label is None


def test_resolve_static_label_nonexistent():
    assert resolve_static_label("nonexistent_key", "A") is None


# ── get_phase_questions ────────────────────────────────────────────────


def test_get_phase_questions_returns_list():
    questions = get_phase_questions("0", {})
    assert isinstance(questions, list)
    assert len(questions) > 0


def test_get_phase_questions_invalid_phase():
    assert get_phase_questions("99", {}) == []


def test_get_phase_questions_appends_free_text():
    questions = get_phase_questions("0", {})
    for q in questions:
        opts = q.get("options")
        if opts:
            assert opts[-1]["label"] == "Ceritakan sendiri..."


def test_get_phase_6_quantitative():
    answers = {"methodology_approach": "A"}  # Kuantitatif
    questions = get_phase_questions("6", answers)
    assert len(questions) > 0
    assert questions[0]["key"] == "visualization_type"


def test_get_phase_6_qualitative():
    answers = {"methodology_approach": "B"}  # Kualitatif
    questions = get_phase_questions("6", answers)
    assert questions[0]["key"] == "visualization_type"


# ── _extract_json_array ────────────────────────────────────────────────


def test_extract_json_array_clean():
    result = _extract_json_array('["A", "B", "C", "D"]')
    assert result == ["A", "B", "C", "D"]


def test_extract_json_array_fenced():
    result = _extract_json_array('```json\n["A", "B", "C", "D"]\n```')
    assert result == ["A", "B", "C", "D"]


def test_extract_json_array_with_think_block():
    result = _extract_json_array(
        "<think>I should generate options</think>\n```json\n[\"A\", \"B\"]\n```"
    )
    assert result == ["A", "B"]


def test_extract_json_array_bracket_fallback():
    result = _extract_json_array("The options are: [\"A\", \"B\", \"C\", \"D\"]")
    assert result == ["A", "B", "C", "D"]


def test_extract_json_array_empty():
    assert _extract_json_array(None) is None
    assert _extract_json_array("") is None
    assert _extract_json_array("no brackets here") is None


# ── generate_ai_options ────────────────────────────────────────────────


@patch("tools.chat.workflow_ai.requests.post")
@patch.dict(os.environ, {"AIOTOMASI_API": "http://test.local", "AIOTOMASI_APIKEY": "testkey"})
def test_generate_ai_options_api_fallback(mock_post):
    clear_ai_options_cache()
    options = generate_ai_options(
        {"id": "2.1", "key": "topik", "question": "What topic?", "depends_on": []},
        {},
    )
    assert len(options) == 4
    assert all(o["value"] in ("A", "B", "C", "D") for o in options)


@patch("tools.chat.workflow_ai.requests.post")
@patch.dict(os.environ, {"AIOTOMASI_API": "http://test.local", "AIOTOMASI_APIKEY": "testkey"})
def test_generate_ai_options_parses_response(mock_post):
    clear_ai_options_cache()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": '["ML", "AI", "Data Mining", "NLP"]'}}]
    }
    mock_post.return_value = mock_resp
    options = generate_ai_options(
        {"id": "2.1", "key": "topik", "question": "Topic?", "depends_on": ["1.1"]},
        {"1.1": "A"},
    )
    assert len(options) == 4
    assert options[0]["label"] == "ML"


# ── _get_fallback_options ──────────────────────────────────────────────


def test_get_fallback_options_returns_4():
    opts = _get_fallback_options("1.4", "title", {})
    assert len(opts) == 4


def test_get_fallback_options_question_specific():
    opts = _get_fallback_options("2.1", "topic", {"field": "A"})
    assert "Machine Learning" in " ".join(o["label"] for o in opts)


# ── validate_workflow ──────────────────────────────────────────────────


def test_validate_workflow_returns_warnings():
    result = validate_workflow({})
    assert "warnings" in result


def test_validate_workflow_no_critical_with_empty():
    result = validate_workflow({})
    assert len(result.get("warnings", [])) == 0


def test_validate_workflow_rq_method_mismatch():
    result = validate_workflow({
        "methodology_approach": "Kualitatif",
        "research_questions": "Seberapa besar pengaruh X terhadap Y?",
    })
    warnings = result.get("warnings", [])
    rq_warnings = [w for w in warnings if w["type"] == "RQ vs Metode"]
    assert len(rq_warnings) >= 1


def test_validate_workflow_scopus_reference_count():
    result = validate_workflow({
        "target_publication": "D",
        "reference_count": "A",
    })
    warnings = result.get("warnings", [])
    citation_warnings = [w for w in warnings if "Sitasi" in w["type"]]
    assert len(citation_warnings) >= 1


# ── question dependency chains ─────────────────────────────────────────


def test_question_dependencies_exist():
    for phase in WORKFLOW_PHASES.values():
        for q in (phase.get("questions") or []):
            deps = q.get("depends_on", [])
            assert isinstance(deps, list), f"{q['id']} deps should be a list"
        for branch in (phase.get("branches") or {}).values():
            for q in (branch.get("questions") or []):
                deps = q.get("depends_on", [])
                assert isinstance(deps, list), f"{q['id']} deps should be a list"


# ── Phase 6 branch conditions ──────────────────────────────────────────


def test_phase_6_quantitative_condition():
    branches = WORKFLOW_PHASES["6"]["branches"]
    fn = branches["quantitative"]["condition"]
    assert fn({"methodology_approach": "A"}) is True
    assert fn({"methodology_approach": "C"}) is True


def test_phase_6_qualitative_condition():
    branches = WORKFLOW_PHASES["6"]["branches"]
    fn = branches["qualitative"]["condition"]
    assert fn({"methodology_approach": "B"}) is True


def test_phase_6_literature_condition():
    branches = WORKFLOW_PHASES["6"]["branches"]
    fn = branches["literature"]["condition"]
    assert fn({"paper_type": "A"}) is True
    assert fn({"paper_type": "D"}) is True
