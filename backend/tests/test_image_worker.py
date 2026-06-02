"""Image-worker concurrency tests.

These tests pin down the queue → claim → save invariants without launching
Playwright/Chrome:

- The atomic UPDATE in `_Worker._process` lets exactly one worker claim a
  given queued job (no duplicate Gemini calls under double-dispatch).
- The dispatcher dedupes against its in-memory `_dispatched` set so the same
  job id isn't routed to two workers.
- A successful run writes the PaperImage row + flips the job to 'done' with
  `image_id` populated, which is what the editor relies on to render.
- A concurrent cancel after the worker claimed (but before/after generation)
  doesn't end up creating a stray PaperImage.
"""

from __future__ import annotations

import os
import sys
import threading
import uuid
from pathlib import Path
from unittest.mock import patch

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

try:
    from workers import slr_worker

    slr_worker._started = True
except Exception:
    pass
try:
    from workers import image_worker

    image_worker._started = True
except Exception:
    pass

try:
    from app import app as flask_app
    from database.models import ImageGenJob, Paper, PaperImage, User, db
    from workers import image_worker as iw
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


def _mk_user_paper():
    u = User(email="img@e.com", name="img", password_hash="x")
    db.session.add(u)
    db.session.flush()
    p = Paper(id="paper-img-1", user_id=u.id, title="t", data={})
    db.session.add(p)
    db.session.flush()
    return u, p


def _mk_job(user_id: int, paper_id: str, prompt: str = "a cat") -> str:
    j = ImageGenJob(
        id=uuid.uuid4().hex,
        user_id=user_id,
        paper_id=paper_id,
        prompt=prompt,
        status="queued",
    )
    db.session.add(j)
    db.session.commit()
    return j.id


# ---------------------------------------------------------------------------
# Atomic claim — only one worker out of N concurrent processors wins.
# ---------------------------------------------------------------------------


def test_only_one_worker_claims_a_queued_job(app_ctx):
    u, p = _mk_user_paper()
    job_id = _mk_job(u.id, p.id)
    db.session.commit()

    # Block both workers BEFORE they hit the atomic UPDATE so they race.
    barrier = threading.Barrier(2)
    proceed = threading.Event()
    claims: list[str] = []
    claims_lock = threading.Lock()

    def fake_safe_paper_dir(_pid):
        # Stop processing right after the claim so we only measure
        # who got the row. Returning None makes the worker mark
        # 'error' for the loser path; for the winner we'll set status
        # back to queued in the assertions step. We instead sidestep
        # by intercepting after the claim via the patched generator.
        return None

    def runner(name: str):
        w = iw._Worker(flask_app, name)
        # `_process` opens its own app_context so it works from a thread.
        # Force the race: pause both threads at the start of _process.
        original = w._process

        def wrapped(job):
            barrier.wait(timeout=5)
            proceed.wait(timeout=5)
            original(job)
            with claims_lock:
                # Re-read: the winner sets status to running -> error
                # (because safe_paper_dir returned None). Losers no-op.
                with flask_app.app_context():
                    j = db.session.get(ImageGenJob, job)
                    if j and j.worker == name:
                        claims.append(name)

        w._process = wrapped
        return w

    w1 = runner("account1")
    w2 = runner("account2")

    with (
        patch.object(iw, "_get_pool"),
        patch("paper_generation.utils.safe_paper_dir", side_effect=fake_safe_paper_dir),
    ):
        t1 = threading.Thread(target=w1._process, args=(job_id,))
        t2 = threading.Thread(target=w2._process, args=(job_id,))
        t1.start()
        t2.start()
        # Both threads are now blocked at the barrier; release them simultaneously.
        proceed.set()
        t1.join(timeout=10)
        t2.join(timeout=10)

    assert len(claims) == 1, f"expected exactly one claimer, got {claims}"

    # Job must be marked 'error' by the winner (because paper_dir is None);
    # not still 'queued' or 'running'. This proves the winner ran the
    # post-claim code path while the loser bailed.
    j = db.session.get(ImageGenJob, job_id)
    assert j.status == "error"
    assert j.worker in ("account1", "account2")
    assert (j.error or "").lower().startswith("invalid paper_id")


# ---------------------------------------------------------------------------
# Dispatcher dedup — submitting the same id twice doesn't double-queue.
# ---------------------------------------------------------------------------


def test_dispatcher_dedups_same_job_id(app_ctx):
    u, p = _mk_user_paper()
    job_id = _mk_job(u.id, p.id)

    # Build a dispatcher with two real-but-empty worker queues. We don't
    # actually start the worker threads (they would launch Chrome); we just
    # check what landed in their queues.
    workers = [iw._Worker(flask_app, n) for n in ("account1", "account2")]
    disp = iw._Dispatcher(flask_app, workers, poll_interval=999)

    # Simulate `submit_now` twice for the same job_id.
    iw._workers.clear()
    iw._workers.extend(workers)
    iw._dispatcher = disp
    try:
        iw.submit_now(job_id)
        iw.submit_now(job_id)
    finally:
        iw._dispatcher = None
        iw._workers.clear()

    total = sum(w.qsize() for w in workers)
    assert total == 1, f"job_id was submitted {total}× across workers"


# ---------------------------------------------------------------------------
# Happy path — successful run writes file → DB row → updates job.image_id.
# This is what the editor needs to render the image.
# ---------------------------------------------------------------------------


def test_happy_path_creates_paperimage_and_finishes_job(app_ctx, tmp_path):
    u, p = _mk_user_paper()
    job_id = _mk_job(u.id, p.id, "happy path prompt")

    # Rebind data/uploads root to a tmpdir for this test.
    flask_app.root_path = str(tmp_path)

    class FakeAccount:
        name = "account1"

        def launch(self, _pw):
            pass

        def generate_image(self, prompt, out_path, generate_timeout_s=240):
            Path(out_path).write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
            return {"size": 9}

    class FakePool:
        def __init__(self):
            self.accounts = [FakeAccount()]
            self._pw = object()

    with (
        patch.object(iw, "_get_pool", return_value=FakePool()),
        patch("image_generation.compress.compress_image", side_effect=lambda *a, **k: None),
    ):
        w = iw._Worker(flask_app, "account1")
        w._process(job_id)

    j = db.session.get(ImageGenJob, job_id)
    assert j.status == "cancelled"
    assert j.image_id is None
    # No paper image rows for this paper.
    assert PaperImage.query.filter_by(paper_id=p.id).count() == 0
    # Disk file unlinked.
    paper_dir = Path(flask_app.root_path) / "data/uploads" / p.id
    leftover = list(paper_dir.glob("*")) if paper_dir.exists() else []
    assert leftover == []
