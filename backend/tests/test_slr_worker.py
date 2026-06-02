"""Tests for slr_worker pure helpers (no thread-boot)."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-real-and-not-short")
os.environ.setdefault("SECRET_KEY", "test-secret-not-real-and-not-default")
os.environ.setdefault("SIGNED_URL_SECRET", "test-signed-url-secret")
os.environ.setdefault("JWT_COOKIE_SECURE", "false")
os.environ.setdefault("SESSION_COOKIE_SECURE", "false")

# Pin started=True so importing app doesn't spin up the pump thread.
try:
    from workers import slr_worker

    slr_worker._started = True
except Exception:  # pragma: no cover
    pass
try:
    from workers import image_worker

    image_worker._started = True
except Exception:
    pass

try:
    from app import app as flask_app
    from database.models import Paper, SlrJob, User, db
    from workers import slr_worker as sw
except Exception as e:  # pragma: no cover
    pytest.skip(f"App bootstrap failed: {e}", allow_module_level=True)


@pytest.fixture()
def app_ctx():
    flask_app.config["TESTING"] = True
    with flask_app.app_context():
        db.drop_all()
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


def test_gen_id_returns_12_char_hex():
    out = sw._gen_id()
    assert isinstance(out, str)
    assert len(out) == 12
    assert re.match(r"^[0-9a-f]{12}$", out)


def test_gen_id_is_unique_across_calls():
    seen = {sw._gen_id() for _ in range(50)}
    assert len(seen) == 50


def test_stage_to_pct_is_monotonic_non_decreasing():
    """Stages must produce monotonically non-decreasing percentages."""
    stages_in_order = [
        ("queued", {}),
        ("fetching", {"sources": ["a"], "total": 1}),
        ("source_done", {"completed": 1, "total": 1}),
        ("dedup_done", {"count": 5}),
        ("scoring", {"count": 5}),
        ("scored", {"count": 5}),
        ("summarizing", {"count": 5}),
        ("summarized", {"done": 5, "total": 5}),
        ("complete", {"top_k": 5, "total": 5}),
    ]
    pcts = [sw._stage_to_pct(stage, info) for stage, info in stages_in_order]
    # queued is unknown → returns 0; the rest must be non-decreasing.
    rest = pcts[1:]
    for a, b in zip(rest, rest[1:]):
        assert a <= b, f"Non-monotonic: {pcts}"
    assert pcts[-1] == 100  # complete = 100


def test_stage_message_returns_non_empty_strings_for_known_stages():
    known = [
        "fetching",
        "source_done",
        "dedup_done",
        "scoring",
        "scored",
        "summarizing",
        "summarized",
        "complete",
    ]
    for stage in known:
        msg = sw._stage_message(
            stage,
            {
                "sources": ["a"],
                "total": 1,
                "count": 1,
                "completed": 1,
                "done": 1,
                "top_k": 1,
                "source": "openalex",
            },
        )
        assert isinstance(msg, str)
        assert msg.strip() != ""


def test_enqueue_slr_job_inserts_queued_row(app_ctx):
    user = User(email="enq@example.com", name="enq")
    user.set_password("xx-not-real-pw")
    db.session.add(user)
    db.session.commit()
    paper = Paper(id="paperENQ01", user_id=user.id, title="t", data={})
    db.session.add(paper)
    db.session.commit()

    job = sw.enqueue_slr_job(
        paper_id=paper.id,
        user_id=user.id,
        query="hello world",
        top_k=20,
        per_source=30,
    )
    assert isinstance(job, SlrJob)
    assert isinstance(job.id, str) and len(job.id) == 12

    row = db.session.query(SlrJob).filter_by(id=job.id).first()
    assert row is not None
    assert row.status == "queued"
    assert int(row.progress or 0) == 0
    assert row.query == "hello world"
    assert row.top_k == 20
    assert row.user_id == user.id
    assert row.paper_id == paper.id
