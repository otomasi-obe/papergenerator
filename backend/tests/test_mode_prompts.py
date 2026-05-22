"""Tests for the mode prompt + tool registry."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mode_prompts  # noqa: E402
from mode_prompts import (  # noqa: E402
    MODE_PROMPTS,
    MODE_TOOLS,
    TIER0_PROMPT,
    get_mode_bundle,
    list_modes,
)


EXPECTED_MODES = {"tier0", "discovery", "slr", "edit", "rapikan", "memory", "casual"}


# ── basic shape ────────────────────────────────────────────────────────────

def test_list_modes_contains_expected():
    modes = set(list_modes())
    assert EXPECTED_MODES.issubset(modes)


def test_get_mode_bundle_returns_tuple():
    out = get_mode_bundle("discovery")
    assert isinstance(out, tuple) and len(out) == 2
    prompt, tools = out
    assert isinstance(prompt, str)
    assert isinstance(tools, list)


def test_get_mode_bundle_unknown_falls_back_to_tier0():
    p, t = get_mode_bundle("does-not-exist")
    assert p == TIER0_PROMPT
    assert t == ["RouteIntent"]


def test_get_mode_bundle_empty_falls_back_to_tier0():
    p, t = get_mode_bundle("")
    assert p == TIER0_PROMPT
    assert t == ["RouteIntent"]


def test_get_mode_bundle_none_falls_back_to_tier0():
    p, t = get_mode_bundle(None)  # type: ignore[arg-type]
    assert p == TIER0_PROMPT


def test_get_mode_bundle_is_case_insensitive():
    p, t = get_mode_bundle("DISCOVERY")
    assert p == MODE_PROMPTS["discovery"]
    assert t == MODE_TOOLS["discovery"]


def test_get_mode_bundle_returns_copy_of_tools():
    _, t1 = get_mode_bundle("edit")
    t1.append("Bogus")
    _, t2 = get_mode_bundle("edit")
    assert "Bogus" not in t2


# ── prompt size constraint ────────────────────────────────────────────────

def test_each_prompt_under_2kb():
    for mode, prompt in MODE_PROMPTS.items():
        size = len(prompt.encode("utf-8"))
        assert size < 2048, f"{mode} prompt is {size} B (>= 2 KB)"


def test_tier0_prompt_is_minimal():
    assert len(TIER0_PROMPT.encode("utf-8")) < 300


def test_memory_prompt_is_short():
    assert len(MODE_PROMPTS["memory"].encode("utf-8")) < 600


# ── tool list constraints ─────────────────────────────────────────────────

def test_tool_lists_unique_within_mode():
    for mode, tools in MODE_TOOLS.items():
        assert len(tools) == len(set(tools)), f"{mode} has duplicate tools"


def test_tool_lists_non_empty_except_casual():
    for mode, tools in MODE_TOOLS.items():
        if mode == "casual":
            assert tools == []
        else:
            assert len(tools) >= 1, f"{mode} has empty tool list"


def test_tier0_only_has_routeintent():
    _, tools = get_mode_bundle("tier0")
    assert tools == ["RouteIntent"]


def test_discovery_has_required_tools():
    _, tools = get_mode_bundle("discovery")
    required = {
        "RunSLR",
        "GetLiterature",
        "ListAttachedFiles",
        "ReadAttachedFile",
        "GenerateFullPaper",
        "ProposeChips",
    }
    assert required.issubset(set(tools))


def test_slr_has_search_tools():
    _, tools = get_mode_bundle("slr")
    assert "RunSLR" in tools
    assert "SearchPapers" in tools
    assert "GetLiterature" in tools


def test_edit_has_propose_tools():
    _, tools = get_mode_bundle("edit")
    propose = [t for t in tools if t.startswith("Propose")]
    assert len(propose) >= 5


def test_rapikan_has_numbering_tool():
    _, tools = get_mode_bundle("rapikan")
    assert "GetPaperNumbering" in tools
    assert "ProposeSection" in tools


def test_memory_excludes_save_and_get():
    _, tools = get_mode_bundle("memory")
    assert "SaveMemory" not in tools
    assert "GetMemory" not in tools
    assert "ListMemory" in tools
    assert "DeleteMemory" in tools


def test_save_memory_not_in_any_mode():
    for mode, tools in MODE_TOOLS.items():
        assert "SaveMemory" not in tools, f"{mode} still has SaveMemory"


# ── prompt content sanity checks ──────────────────────────────────────────

def test_discovery_prompt_mentions_key_markers():
    p = MODE_PROMPTS["discovery"]
    assert "key=jurusan" in p
    assert "key=topik" in p
    assert "key=metode" in p
    assert "AskQuestions" in p


def test_tier0_prompt_mentions_routeintent():
    assert "RouteIntent" in TIER0_PROMPT


def test_module_exports_public_api():
    assert hasattr(mode_prompts, "get_mode_bundle")
    assert hasattr(mode_prompts, "list_modes")
    assert hasattr(mode_prompts, "TIER0_PROMPT")
    assert hasattr(mode_prompts, "MODE_PROMPTS")
    assert hasattr(mode_prompts, "MODE_TOOLS")
