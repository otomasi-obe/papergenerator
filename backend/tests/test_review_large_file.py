"""Unit tests for chat_tools._review_large_file.

The tool inspects an attached PaperFile and either:
  - returns a PROPOSAL_PREFIX-wrapped JSON payload {kind: "file_review", ...}
    when the file's word count is > 3000 (so the chat UI can prompt the user
    to pick which sections to ingest), or
  - falls back to read_attached_file behaviour (return the full text) when
    the file fits comfortably in context.

If Agent G hasn't landed `_review_large_file` yet, the module skips with a
clear reason.
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
    from models import Paper, PaperFile, User, db
    Paper.__table__.c.data.type = JSON()
except Exception as e:  # pragma: no cover
    pytest.skip(f"chat_tools bootstrap failed: {e}", allow_module_level=True)


if not hasattr(chat_tools, "_review_large_file"):
    pytest.skip(
        "chat_tools._review_large_file not implemented yet "
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

    paper = Paper(id="paperRL1", user_id=user.id, title="t", data={})
    db.session.add(paper)
    db.session.commit()
    return user, paper


def _attach_file(paper, user, name, text, ext=".pdf"):
    f = PaperFile(
        paper_id=paper.id,
        user_id=user.id,
        filename=f"stored_{name}",
        original_name=name,
        ext=ext,
        size_bytes=len(text.encode("utf-8")),
        file_path=f"{paper.id}/{name}",
        extracted_text=text,
    )
    db.session.add(f)
    db.session.commit()
    return f


def _call(paper_id, user_id, args):
    return chat_tools._review_large_file(paper_id, user_id, args)


def _payload(out):
    """If the tool returned a PROPOSAL_PREFIX payload, parse the trailing JSON."""
    assert isinstance(out, str)
    if out.startswith(chat_tools.PROPOSAL_PREFIX):
        return json.loads(out[len(chat_tools.PROPOSAL_PREFIX):])
    return None


# ─── happy paths ─────────────────────────────────────────────────────────


def test_large_file_returns_proposal(app):
    user, paper = _make_user_paper()
    # 5000 words clearly above the 3000 threshold.
    big_text = ("lorem ipsum dolor sit amet " * 1000).strip()  # 5000 tokens
    f = _attach_file(paper, user, "huge.pdf", big_text)

    out = _call(paper.id, user.id, {"file_id": f.id})
    payload = _payload(out)
    assert payload is not None, f"expected PROPOSAL_PREFIX payload, got: {out[:120]}"

    assert payload.get("kind") == "file_review"
    assert payload.get("file_id") == f.id
    assert payload.get("filename") == "huge.pdf"
    wc = payload.get("word_count")
    assert isinstance(wc, int) and wc > 3000, f"word_count too small: {wc}"
    assert payload.get("head"), "head excerpt missing"
    assert payload.get("tail"), "tail excerpt missing"
    # head + tail should each be much shorter than the full text.
    assert len(payload["head"]) < len(big_text)
    assert len(payload["tail"]) < len(big_text)
    # Suggested section kinds + needs_user_pick flag.
    assert payload.get("needs_user_pick") is True
    sk = payload.get("suggested_kinds")
    assert isinstance(sk, list) and sk, f"suggested_kinds empty: {sk}"


def test_small_file_returns_full_text(app):
    user, paper = _make_user_paper()
    small_text = "This is a short paper. It has fewer than 100 words."
    f = _attach_file(paper, user, "tiny.txt", small_text, ext=".txt")

    out = _call(paper.id, user.id, {"file_id": f.id})
    # No PROPOSAL_PREFIX — falls through to read_attached_file behaviour.
    assert not out.startswith(chat_tools.PROPOSAL_PREFIX), (
        f"small file should not produce a proposal: {out[:120]}"
    )
    # The original text must show up in the output.
    assert small_text in out
    # Filename should be surfaced in the header (matches read_attached_file).
    assert "tiny.txt" in out


def test_borderline_under_threshold(app):
    """Exactly 2999 words → still small file → return full text."""
    user, paper = _make_user_paper()
    text = ("word " * 2999).strip()
    f = _attach_file(paper, user, "border.pdf", text)

    out = _call(paper.id, user.id, {"file_id": f.id})
    assert not out.startswith(chat_tools.PROPOSAL_PREFIX), (
        "2999-word file should not trigger the proposal path"
    )


def test_borderline_over_threshold(app):
    """3001 words → proposal path triggers."""
    user, paper = _make_user_paper()
    text = ("word " * 3001).strip()
    f = _attach_file(paper, user, "over.pdf", text)

    out = _call(paper.id, user.id, {"file_id": f.id})
    payload = _payload(out)
    assert payload is not None, f"expected proposal for 3001-word file, got: {out[:120]}"
    assert payload.get("kind") == "file_review"


# ─── error cases ─────────────────────────────────────────────────────────


def test_missing_file_id(app):
    user, paper = _make_user_paper()
    out = _call(paper.id, user.id, {})
    assert isinstance(out, str)
    low = out.lower()
    assert "file_id" in low or "error" in low or "required" in low


def test_file_not_found(app):
    user, paper = _make_user_paper()
    out = _call(paper.id, user.id, {"file_id": 9999999})
    low = out.lower()
    assert "not found" in low or "error" in low


def test_no_paper_id(app):
    user, _ = _make_user_paper()
    out = _call("", user.id, {"file_id": 1})
    low = out.lower()
    assert "no paper" in low or "error" in low or "not found" in low


def test_cross_user_file_rejected(app):
    """User B should not be able to review user A's file."""
    user_a, paper = _make_user_paper()
    user_b = User(email="bob@example.com", name="Bob")
    user_b.set_password("not-real-pw-12345")
    db.session.add(user_b)
    db.session.commit()

    text = "small text"
    f = _attach_file(paper, user_a, "alice.pdf", text)

    out = _call(paper.id, user_b.id, {"file_id": f.id})
    low = out.lower()
    assert "not found" in low or "error" in low or "unauthorized" in low
