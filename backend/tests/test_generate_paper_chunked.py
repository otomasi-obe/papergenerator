"""Tests for the chunked paper generator orchestrator.

Covers:
  - test_full_run    — checkpoint cadence + monotonic progress
  - test_cancel      — cancel_check at section_3 raises GenerationCancelled
                       with partial paper containing outline + sections 1, 2
  - test_resume      — resume_state with chunks_done = [outline, section_1,
                       section_2] skips those chunks and only invokes
                       section_3..5 + references + combine

These tests mock the underlying API helpers (_generate_outline,
_generate_section, _generate_references) so no network is involved.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

os.environ.setdefault("AIOTOMASI_API", "https://example.invalid/api")
os.environ.setdefault("AIOTOMASI_APIKEY", "test-key-not-real")

import paper_generation.chunked as gpc  # noqa: E402
from paper_generation.chunked import (  # noqa: E402
    GenerationCancelled,
    generate_paper_json_chunked,
)

# ─── Fixtures ────────────────────────────────────────────────────────────


def _fake_outline(*_a, **_kw):
    return {
        "title": "Fake Paper Title",
        "abstract": "Fake abstract.",
        "keywords": ["k1", "k2"],
        "section_titles": {
            "section1": "INTRODUCTION",
            "section2": "RELATED WORK",
            "section3": "METHODOLOGY",
            "section4": "RESULTS",
            "section5": "CONCLUSION",
        },
    }


def _fake_section(section_num, *_a, **_kw):
    # Mimic the shape produced by the real _generate_section.
    return {
        "title": f"FAKE SECTION {section_num}",
        "content": [
            {"id": "text", "text": f"Body for section {section_num}."},
        ],
    }


def _fake_references(*_a, **_kw):
    return [f"[{i}] Fake reference {i}." for i in range(1, 6)]


@pytest.fixture()
def patched_generators():
    """Patch the three internal chunk callers so tests run offline."""
    with (
        patch.object(gpc, "_generate_outline", side_effect=_fake_outline) as out_mock,
        patch.object(gpc, "_generate_section", side_effect=_fake_section) as sec_mock,
        patch.object(gpc, "_generate_references", side_effect=_fake_references) as ref_mock,
    ):
        yield {"outline": out_mock, "section": sec_mock, "references": ref_mock}


# ─── test_full_run ───────────────────────────────────────────────────────


def test_full_run_emits_eight_checkpoints_with_monotonic_progress(patched_generators):
    """End-to-end run lands 8 checkpoints in order with non-decreasing progress."""
    events: list[tuple[str, int]] = []

    def cb(stage, progress, partial):
        events.append((stage, progress))
        # Partial should always be a dict — never None.
        assert isinstance(partial, dict)

    paper = generate_paper_json_chunked(
        judul="Demo paper",
        custom_prompt="",
        api_key="x",
        base_url="http://x.invalid",
        model="V-OPUS",
        checkpoint_cb=cb,
    )

    stages = [s for s, _ in events]
    assert stages == [
        "outline",
        "section_1",
        "section_2",
        "section_3",
        "section_4",
        "section_5",
        "references",
        "combine",
    ]

    progresses = [p for _, p in events]
    assert progresses == sorted(progresses), "progress must be non-decreasing"
    assert progresses[0] >= 1
    assert progresses[-1] == 100

    # Final paper has the canonical shape.
    assert paper["title"] == "Fake Paper Title"
    assert len(paper["sections"]) == 5
    assert paper["references"]

    # Each underlying chunk fn ran the expected number of times.
    assert patched_generators["outline"].call_count == 1
    assert patched_generators["section"].call_count == 5
    assert patched_generators["references"].call_count == 1


# ─── test_cancel ─────────────────────────────────────────────────────────


def test_cancel_at_section_3_raises_with_partial_outline_plus_two_sections(patched_generators):
    """cancel_check() returning True at section_3 raises GenerationCancelled.

    Partial state captured by checkpoint_cb must contain the outline plus the
    two sections that completed before the cancel was observed.
    """
    last_partial: dict = {}

    def cb(stage, progress, partial):
        # Snapshot every checkpoint so we can inspect what survived the cancel.
        last_partial.update(partial)

    # The orchestrator polls cancel_check BEFORE each chunk. Returning True
    # the first time the check is invoked while the next chunk would be
    # section_3 raises GenerationCancelled("section_3"). Outline + section_1
    # + section_2 finish first because their pre-checks already returned False.
    call_count = {"n": 0}

    def cancel_check():
        # Trigger cancel right before section_3's chunk runs.
        # Order of checks: outline, section_1, section_2, section_3, ...
        # We want it to fire on the section_3 pre-check (the 4th call).
        call_count["n"] += 1
        return call_count["n"] >= 4

    with pytest.raises(GenerationCancelled) as exc_info:
        generate_paper_json_chunked(
            judul="Demo paper",
            custom_prompt="",
            api_key="x",
            base_url="http://x.invalid",
            model="V-OPUS",
            checkpoint_cb=cb,
            cancel_check=cancel_check,
        )

    assert exc_info.value.stage == "section_3"

    # Outline completed.
    assert "outline" in last_partial
    # Sections 1 and 2 landed; 3+ never started.
    assert len(last_partial.get("sections") or []) == 2
    # References never ran.
    assert "references" not in last_partial or not last_partial.get("references")

    # Internal call counts confirm 5th section + references never invoked.
    assert patched_generators["outline"].call_count == 1
    assert patched_generators["section"].call_count == 2
    assert patched_generators["references"].call_count == 0


# ─── test_resume ─────────────────────────────────────────────────────────


def test_resume_skips_completed_chunks(patched_generators):
    """Feeding resume_state with outline + sections 1-2 done means only
    sections 3, 4, 5, references, and combine should run."""
    resume_state = {
        "chunks_done": ["outline", "section_1", "section_2"],
        "partial_paper": {
            "outline": _fake_outline(),
            "title": "Fake Paper Title",
            "abstract": "Fake abstract.",
            "keywords": ["k1", "k2"],
            "sections": [
                _fake_section(1),
                _fake_section(2),
            ],
        },
    }

    events: list[str] = []

    def cb(stage, progress, partial):
        events.append(stage)

    paper = generate_paper_json_chunked(
        judul="Demo paper",
        custom_prompt="",
        api_key="x",
        base_url="http://x.invalid",
        model="V-OPUS",
        checkpoint_cb=cb,
        resume_state=resume_state,
    )

    # Outline + sections 1-2 are SKIPPED (no checkpoint, no fn call).
    assert "outline" not in events
    assert "section_1" not in events
    assert "section_2" not in events
    # Sections 3-5, references, combine all run.
    assert events == ["section_3", "section_4", "section_5", "references", "combine"]

    # _generate_outline never called on resume.
    assert patched_generators["outline"].call_count == 0
    # Only sections 3, 4, 5 regenerated.
    assert patched_generators["section"].call_count == 3
    assert patched_generators["references"].call_count == 1

    # Final paper still has 5 sections (the cached two + 3 fresh).
    assert len(paper["sections"]) == 5


# ─── test_full_context_injection ─────────────────────────────────────────


def test_load_full_context_helper_handles_empty_inputs():
    """_load_full_context returns empty string when no paper_id/conv_id given,
    and never raises on missing data."""
    # No paper_id and no conv_id should give empty result
    result = gpc._load_full_context(paper_id=None, conv_id=None)
    assert result == "" or result.strip() == ""


def test_load_full_context_under_30kb_cap():
    """_load_full_context output must stay under 30KB even with large inputs.

    This guards against context bloat — the chunked generator already pushes
    50-130KB total prompt size, so the context injection must respect its budget.
    """
    # Use bogus paper_id; DB queries will fail/return empty inside try-except
    # but the function should still return a string under cap.
    result = gpc._load_full_context(paper_id="nonexistent", conv_id="nonexistent")
    assert isinstance(result, str)
    assert len(result) <= 30_000


def test_references_prompt_contains_literature_catalog():
    """When custom_prompt carries a Literature catalog block, the references
    chunk's system prompt must inline those entries verbatim (not invent refs).
    """
    fake_lit_block = (
        "## Literature catalog (use these as the actual reference list)\n"
        "[L1] Sleep/Wake MAC for IoT — Smith et al. (2023) DOI: 10.1234/abc\n"
        "[L2] Energy Efficiency in WSN — Chen, Wang (2022) in IEEE Trans WSN\n"
    )

    captured_messages = []

    def fake_call(messages, *_a, **_kw):
        captured_messages.extend(messages)
        return ('{"references": ["[1] Smith et al. 2023.", "[2] Chen 2022."]}', "test-model")

    outline = {"title": "Test", "abstract": "abs", "keywords": ["k"]}
    sections = [{"title": "INTRODUCTION", "content": [{"id": "text", "text": "Cited [L1] [L2]."}]}]

    with patch.object(gpc, "_call_aiotomasi_with_fallback", side_effect=fake_call):
        refs = gpc._generate_references(
            outline,
            sections,
            style=None,
            api_key="x",
            base_url="http://x.invalid",
            model="V-OPUS",
            custom_prompt=fake_lit_block,
        )

    # System prompt should mention the curated literature entries.
    sys_prompt = next((m["content"] for m in captured_messages if m["role"] == "system"), "")
    assert "Sleep/Wake MAC for IoT" in sys_prompt or "Smith" in sys_prompt
    assert "Chen" in sys_prompt
    # AI should not be told to invent references when catalog is provided.
    assert "Do NOT" in sys_prompt or "DO NOT" in sys_prompt
    # Returned refs come from the fake call.
    assert refs == ["[1] Smith et al. 2023.", "[2] Chen 2022."]
