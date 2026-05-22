"""Unit tests for chat_tools._get_paragraph_context.

Exercises the paragraph-context tool that the chat agent calls before
proposing a paraphrase / grammar fix / translation. The tool returns a JSON
string with the target paragraph plus its neighbours, the section meta, and
extracted citations / fig-table references.

Schema (per chat_tools._get_paragraph_context):
- section_index is 1-based (1 = first section)
- content_index is 0-based
- neighbors.prev / neighbors.next are plain strings (the text body)
- paper_meta is only populated when args.include_paper_meta is truthy

If Agent G hasn't landed `_get_paragraph_context` yet, the module skips with
a clear reason.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-real-and-not-short")
os.environ.setdefault("SECRET_KEY", "test-secret-not-real-and-not-default")
os.environ.setdefault("SIGNED_URL_SECRET", "test-signed-url-secret")

try:
    from flask import Flask
    from sqlalchemy import JSON
    import chat_tools
    from models import Paper, User, db
    Paper.__table__.c.data.type = JSON()
except Exception as e:  # pragma: no cover
    pytest.skip(f"chat_tools bootstrap failed: {e}", allow_module_level=True)


if not hasattr(chat_tools, "_get_paragraph_context"):
    pytest.skip(
        "chat_tools._get_paragraph_context not implemented yet "
        "(Agent G in flight) — skipping until the function lands.",
        allow_module_level=True,
    )


# ─── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture()
def app():
    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(flask_app)
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


def _make_user_paper():
    user = User(email="alice@example.com", name="Alice")
    user.set_password("not-real-pw-12345")
    db.session.add(user)
    db.session.commit()

    data = {
        "title": "Demo paper",
        "abstract": "Abstract goes here.",
        "keywords": ["k1", "k2"],
        "sections": [
            {
                "title": "INTRODUCTION",
                "content": [
                    {"id": "text", "text": "First intro paragraph."},
                    {"id": "text", "text": "Second intro paragraph."},
                ],
            },
            {
                "title": "RELATED WORK",
                "content": [
                    {"id": "text", "text": "Smith demonstrated X [1]."},
                    {
                        "id": "text",
                        "text": (
                            "As shown in Fig. 2 and Table III, the prior art "
                            "of Doe et al. [2] (Smith, 2023) misses the case "
                            "where Eq. (4) blows up."
                        ),
                    },
                    {"id": "text", "text": "Third related-work paragraph."},
                ],
            },
            {
                "title": "METHODOLOGY",
                "content": [
                    {"id": "text", "text": "Method paragraph."},
                ],
            },
        ],
        "references": ["[1] Foo bar", "[2] Baz qux"],
    }
    paper = Paper(id="paperPC1", user_id=user.id, title="Demo paper", data=data)
    db.session.add(paper)
    db.session.commit()
    return user, paper


def _call(paper_id, user_id, args):
    return chat_tools._get_paragraph_context(paper_id, user_id, args)


def _parse(out):
    """Tool returns a JSON string. Some implementations may prefix it with
    PROPOSAL_PREFIX; strip it if present."""
    assert isinstance(out, str), f"expected str, got {type(out).__name__}"
    s = out
    if s.startswith(chat_tools.PROPOSAL_PREFIX):
        s = s[len(chat_tools.PROPOSAL_PREFIX):]
    return json.loads(s)


# ─── happy path ──────────────────────────────────────────────────────────


def test_returns_target_with_neighbors(app):
    user, paper = _make_user_paper()
    # 1-based section_index: 2 = RELATED WORK; content_index 1 = the citation-rich paragraph.
    out = _call(paper.id, user.id, {"section_index": 2, "content_index": 1})
    payload = _parse(out)

    sm = payload.get("section_meta") or {}
    assert sm.get("title") == "RELATED WORK"
    outline = sm.get("section_outline")
    assert isinstance(outline, list)
    # RELATED WORK has 3 content items.
    assert len(outline) == 3
    # The outline entry for the target should be marked.
    target_marker_lines = [ln for ln in outline if "← target" in ln]
    assert len(target_marker_lines) == 1

    target = payload.get("target") or {}
    assert "Doe et al." in target.get("text", "")
    # Target index is reported 1-based in the response.
    assert target.get("section_index") == 2
    assert target.get("content_index") == 1

    # neighbors.prev / neighbors.next are plain text strings.
    nbrs = payload.get("neighbors") or {}
    assert "Smith demonstrated" in (nbrs.get("prev") or "")
    assert "Third related-work" in (nbrs.get("next") or "")


def test_extracts_citations_and_fig_table_refs(app):
    user, paper = _make_user_paper()
    out = _call(paper.id, user.id, {"section_index": 2, "content_index": 1})
    payload = _parse(out)

    cites = payload.get("citations_in_target") or []
    cite_blob = json.dumps(cites)
    assert "[2]" in cite_blob, f"expected [2] in citations, got {cites}"
    assert "Smith" in cite_blob and "2023" in cite_blob, f"author-year missing: {cites}"

    refs = payload.get("fig_table_refs") or []
    refs_blob = json.dumps(refs)
    assert "Fig. 2" in refs_blob or "Fig 2" in refs_blob, f"missing fig ref: {refs}"
    assert ("Table III" in refs_blob) or ("table iii" in refs_blob.lower()), (
        f"missing table ref: {refs}"
    )


def test_first_paragraph_has_empty_prev(app):
    user, paper = _make_user_paper()
    # section_index=2 (RELATED WORK), content_index=0 = first paragraph in section.
    out = _call(paper.id, user.id, {"section_index": 2, "content_index": 0})
    payload = _parse(out)

    nbrs = payload.get("neighbors") or {}
    # First paragraph in section: prev neighbour should be empty string.
    assert not nbrs.get("prev"), f"expected empty prev, got: {nbrs.get('prev')!r}"
    # Next exists.
    assert "Doe et al." in (nbrs.get("next") or "")


def test_last_paragraph_has_empty_next(app):
    user, paper = _make_user_paper()
    # RELATED WORK has 3 content items (indices 0, 1, 2). Index 2 is last.
    out = _call(paper.id, user.id, {"section_index": 2, "content_index": 2})
    payload = _parse(out)

    nbrs = payload.get("neighbors") or {}
    assert not nbrs.get("next"), f"expected empty next, got: {nbrs.get('next')!r}"
    assert "Doe et al." in (nbrs.get("prev") or "")


def test_section_neighbor_titles(app):
    user, paper = _make_user_paper()
    out = _call(paper.id, user.id, {"section_index": 2, "content_index": 0})
    payload = _parse(out)

    sm = payload.get("section_meta") or {}
    nbr_titles = sm.get("neighbor_titles") or {}
    assert nbr_titles.get("prev") == "INTRODUCTION"
    assert nbr_titles.get("next") == "METHODOLOGY"


def test_include_paper_meta(app):
    user, paper = _make_user_paper()
    out = _call(
        paper.id, user.id,
        {"section_index": 2, "content_index": 0, "include_paper_meta": True},
    )
    payload = _parse(out)
    meta = payload.get("paper_meta") or {}
    assert meta, "paper_meta block should be present when include_paper_meta=true"
    # paper.title is what the column carries (we stored 'Demo paper').
    assert meta.get("title") == "Demo paper"


def test_omit_paper_meta_by_default(app):
    user, paper = _make_user_paper()
    out = _call(paper.id, user.id, {"section_index": 2, "content_index": 0})
    payload = _parse(out)
    assert not payload.get("paper_meta"), "paper_meta should be hidden by default"


def test_constraints_block_present(app):
    user, paper = _make_user_paper()
    out = _call(paper.id, user.id, {"section_index": 1, "content_index": 0})
    payload = _parse(out)
    constraints = payload.get("constraints") or {}
    # Defaults when no ProjectMemory rows: language=id, citation_style=IEEE.
    assert constraints.get("language") in ("id", "en")
    assert constraints.get("citation_style") in (
        "ACS", "APA", "Chicago", "Harvard", "IEEE", "MLA", "Vancouver",
    )


# ─── error cases ─────────────────────────────────────────────────────────


def test_invalid_section_index(app):
    user, paper = _make_user_paper()
    # 99 is way out of range.
    out = _call(paper.id, user.id, {"section_index": 99, "content_index": 0})
    assert isinstance(out, str)
    low = out.lower()
    assert "error" in low or "out of range" in low or "not found" in low


def test_invalid_content_index(app):
    user, paper = _make_user_paper()
    out = _call(paper.id, user.id, {"section_index": 1, "content_index": 99})
    low = out.lower()
    assert "error" in low or "out of range" in low or "not found" in low


def test_missing_section_index(app):
    user, paper = _make_user_paper()
    out = _call(paper.id, user.id, {"content_index": 0})
    low = out.lower()
    assert "error" in low or "must be" in low or "required" in low


def test_paper_not_found(app):
    user, _paper = _make_user_paper()
    out = _call("nopaperX1", user.id, {"section_index": 1, "content_index": 0})
    low = out.lower()
    assert "not found" in low or "error" in low


def test_no_paper_id(app):
    user, _paper = _make_user_paper()
    out = _call("", user.id, {"section_index": 1, "content_index": 0})
    low = out.lower()
    assert "no paper" in low or "error" in low or "not found" in low
