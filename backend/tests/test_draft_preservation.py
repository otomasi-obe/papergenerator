"""Unit tests for draft_preservation module."""
from __future__ import annotations

import pytest

from tools.paperfull.draft_preservation import (
    split_extracted_source,
    classify_uploaded_text,
    parse_draft_sections,
    collect_draft_manifest,
    apply_verbatim_drafts,
    draft_prompt_block,
    assert_verbatim_preserved,
)


def test_split_extracted_source():
    raw = "=== Extracted from: my_draft.docx ===\n\nAbstract\nThis is the abstract text."
    name, body = split_extracted_source(raw)
    assert name == "my_draft.docx"
    assert body.startswith("Abstract")


def test_classify_raw_data():
    raw = "=== Extracted from: data.csv ===\n\nCol1,Col2\n1,2\n3,4"
    result = classify_uploaded_text(raw)
    assert result["kind"] == "raw_data"
    assert result["confidence"] == 1.0


def test_classify_narrative_draft():
    draft = """=== Extracted from: my_paper.docx ===\n\nAbstract\nThis is a substantial abstract paragraph that discusses the problem and methods in detail.\n\nIntroduction\nThis introduction provides extensive background about the research gap and objectives.\n\nMethodology\nThe methodology section describes the experimental design with sufficient narrative detail.\n\nResults\nHere we present the findings with thorough discussion.\n\nDiscussion\nThe discussion interprets the results in context of existing literature.\n\nConclusion\nThe conclusion summarizes contributions and future work."""
    result = classify_uploaded_text(draft)
    assert result["kind"] == "narrative_draft"
    assert result["confidence"] > 0.8
    assert any("headings" in r for r in result["reasons"])


def test_classify_reference_context():
    ref = "=== Extracted from: related_paper.pdf ===\n\nSome generic text without clear academic structure."
    result = classify_uploaded_text(ref)
    assert result["kind"] == "reference_context"


def test_parse_draft_sections():
    draft = """=== Extracted from: draft.docx ===\n\nAbstract\nAbstract text here.\n\nIntroduction\nIntroduction text here.\n\nMethodology\nMethod text here.\n\nResults\nResults text here.\n\nDiscussion\nDiscussion text here.\n\nConclusion\nConclusion text here."""
    parsed = parse_draft_sections(draft)
    assert "abstract" in parsed["sections"]
    assert "introduction" in parsed["sections"]
    assert "methodology" in parsed["sections"]
    assert "results" in parsed["sections"]
    assert "discussion" in parsed["sections"]
    assert "conclusion" in parsed["sections"]
    for section in parsed["sections"].values():
        assert "sha256" in section
        assert len(section["sha256"]) == 64


def test_collect_draft_manifest():
    draft = """=== Extracted from: draft.docx ===\n\nAbstract\nAbstract text.\n\nIntroduction\nIntro text.\n\nMethodology\nMethod text."""
    data = """=== Extracted from: data.csv ===\n\nCol1,Col2\n1,2"""
    ref = """=== Extracted from: paper.pdf ===\n\nSome reference text."""
    data_texts, reference_texts, manifest = collect_draft_manifest([draft, data, ref])
    assert len(data_texts) == 1
    assert len(reference_texts) == 2  # draft goes to reference too
    assert len(manifest["drafts"]) == 1
    assert "abstract" in manifest["drafts"][0]["sections"]


def test_apply_verbatim_drafts_full_match():
    paper = {
        "abstract": "This is the abstract text.",
        "section1": {"title": "INTRODUCTION", "content": [{"id": "text", "text": "Intro text."}]},
        "section2": {"title": "METHODOLOGY", "content": [{"id": "text", "text": "Method text."}]},
        "section3": {"title": "RESULTS", "content": [{"id": "text", "text": "Results text."}]},
        "section4": {"title": "DISCUSSION", "content": [{"id": "text", "text": "Discussion text."}]},
        "section5": {"title": "CONCLUSION", "content": [{"id": "text", "text": "Conclusion text."}]},
    }
    draft = """=== Extracted from: draft.docx ===\n\nAbstract\nThis is the abstract text.\n\nIntroduction\nIntro text.\n\nMethodology\nMethod text.\n\nResults\nResults text.\n\nDiscussion\nDiscussion text.\n\nConclusion\nConclusion text."""
    data_texts, ref_texts, manifest = collect_draft_manifest([draft])
    audit = apply_verbatim_drafts(paper, manifest)
    assert audit["status"] == "verified"
    assert audit["exact_matches"] == 6
    assert audit["mismatches"] == 0
    assert_verbatim_preserved(audit)


def test_apply_verbatim_drafts_enforces_exact():
    """Overlay replaces AI content with draft content; final paper matches exactly."""
    paper = {
        "abstract": "AI generated abstract.",
        "section1": {"title": "INTRODUCTION", "content": [{"id": "text", "text": "AI generated intro."}]},
        "section2": {"title": "METHODOLOGY", "content": [{"id": "text", "text": "AI generated method."}]},
    }
    draft = """=== Extracted from: draft.docx ===\n\nAbstract\nExact abstract text.\n\nIntroduction\nExact intro text.\n\nMethodology\nExact method text."""
    data_texts, ref_texts, manifest = collect_draft_manifest([draft])
    audit = apply_verbatim_drafts(paper, manifest)
    # Overlay enforces exact match
    assert audit["status"] == "verified"
    assert audit["exact_matches"] == 3
    expected = manifest["drafts"][0]["sections"]
    assert paper["abstract"] == expected["abstract"]["content"]
    items = [item for item in paper["section1"]["content"] if item.get("id") == "text"]
    assert items[0]["text"] == expected["introduction"]["content"]
    items = [item for item in paper["section2"]["content"] if item.get("id") == "text"]
    assert items[0]["text"] == expected["methodology"]["content"]
    assert_verbatim_preserved(audit)


def test_apply_verbatim_drafts_no_drafts_not_applicable():
    """No drafts -> status not_applicable, paper unchanged."""
    paper = {"section1": {"title": "INTRODUCTION", "content": [{"id": "text", "text": "AI generated intro."}]}}
    data_texts, ref_texts, manifest = collect_draft_manifest([])
    audit = apply_verbatim_drafts(paper, manifest)
    assert audit["status"] == "not_applicable"
    assert audit["protected_sections"] == 0


def test_draft_prompt_block():
    draft = """=== Extracted from: draft.docx ===\n\nAbstract\nAbstract text.\n\nIntroduction\nIntro text."""
    data_texts, ref_texts, manifest = collect_draft_manifest([draft])
    block = draft_prompt_block(manifest)
    assert "PROTECTED VERBATIM" in block
    assert "Abstract" in block
    assert "sha256" in block.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])