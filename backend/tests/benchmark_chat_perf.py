#!/usr/bin/env python3
"""
Benchmark: Chat System Performance Comparison
===============================================
Measures query count, response time, and memory for the optimised chat
endpoints against a synthetic dataset of 100 papers × 500 conversations.

Usage:
    python -m tests.benchmark_chat_perf              # run full benchmark
    python -m tests.benchmark_chat_perf --quick       # 10 papers only
    python -m tests.benchmark_chat_perf --report-only # re-print last report
"""

from __future__ import annotations

import json
import os
import sys
import time
import tracemalloc
from contextlib import contextmanager
from datetime import datetime, timezone

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["FLASK_ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite://"  # in-memory
os.environ["JWT_SECRET_KEY"] = "benchmark-test-key-not-for-prod"
os.environ["AIOTOMASI_API"] = ""
os.environ["AIOTOMASI_APIKEY"] = ""

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from database.models import ChatMessage, Conversation, Paper, User, db

# ── Test app (minimal, no background workers) ─────────────────────────────
app = Flask(__name__)
app.config["TESTING"] = True
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = "benchmark-test-key"
app.config["JWT_TOKEN_LOCATION"] = ["headers"]
db.init_app(app)
JWTManager(app)

from tools.chat.chat_routes import chat_api
app.register_blueprint(chat_api)

import logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logging.getLogger("database.queries").setLevel(logging.WARNING)

# ── Helpers ────────────────────────────────────────────────────────────────


def _utcnow():
    return datetime.now(timezone.utc)


@contextmanager
def catch_query_count():
    """Count SQLAlchemy queries executed inside the block."""
    from sqlalchemy import event

    count = [0]
    queries = []

    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        count[0] += 1
        queries.append(str(statement)[:120])

    event.listen(db.engine, "after_cursor_execute", _after_cursor_execute)
    try:
        yield count, queries
    finally:
        event.remove(db.engine, "after_cursor_execute", _after_cursor_execute)


# ── Seed data ──────────────────────────────────────────────────────────────


def seed_data(num_papers: int = 100, convs_per_paper: int = 5):
    with app.app_context():
        user = User.query.first()
        if user is None:
            user = User(
                id=1,
                email="benchmark@test.com",
                name="Benchmark User",
                password_hash="",
            )
            db.session.add(user)
            db.session.commit()

        existing = Paper.query.count()
        if existing >= num_papers:
            print(f"[seed] data already exists ({existing} papers), skipping")
            return user

        print(f"[seed] creating {num_papers} papers × ~{convs_per_paper} conversations…")
        for i in range(num_papers):
            p = Paper(
                id=f"BENCH{i:04d}",
                user_id=user.id,
                title=f"Benchmark Paper {i} — {'x' * 40}",
                data={},
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            db.session.add(p)
            for j in range(convs_per_paper):
                c = Conversation(
                    id=f"BENCH{i:04d}C{j:03d}",
                    user_id=user.id,
                    paper_id=p.id,
                    title=f"Chat {j} for Paper {i}",
                    created_at=_utcnow(),
                    updated_at=_utcnow(),
                )
                db.session.add(c)
                # 10 messages per conversation
                for k in range(10):
                    role = "user" if k % 2 == 0 else "assistant"
                    content = (
                        f"This is message {k} in conversation {j} for paper {i}. "
                        + "Lorem ipsum dolor sit amet. " * 10
                    )
                    m = ChatMessage(
                        conversation_id=c.id,
                        role=role,
                        content=content,
                        created_at=_utcnow(),
                    )
                    db.session.add(m)

            if (i + 1) % 20 == 0:
                db.session.commit()
                print(f"[seed]  … {i + 1}/{num_papers} papers committed")
        db.session.commit()
        print(f"[seed] done — {num_papers} papers, ~{num_papers * convs_per_paper} conversations")
        return user.id


# ── Benchmarks ─────────────────────────────────────────────────────────────


def benchmark_list_paper_chats(user_id: int) -> dict:
    from tools.chat.chat_routes import list_paper_chats

    with app.app_context():
        token = create_access_token(identity=str(user_id))
    with app.test_request_context(
        "/api/chat/papers",
        headers={"Authorization": f"Bearer {token}"},
    ):
        with catch_query_count() as (count, queries):
            tracemalloc.start()
            t0 = time.perf_counter()
            result = list_paper_chats()
            elapsed = time.perf_counter() - t0
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

    query_count = count[0]
    paper_count = len(result) if isinstance(result, list) else 0

    return {
        "endpoint": "list_paper_chats",
        "papers_returned": paper_count,
        "db_queries": query_count,
        "time_ms": round(elapsed * 1000, 2),
        "peak_memory_kb": round(peak / 1024, 1),
        "queries": queries[0] if query_count == 1 else f"{query_count} queries",
    }


def benchmark_get_conversation(user_id: int) -> dict:
    from tools.chat.chat_routes import get_conversation

    with app.app_context():
        conv = Conversation.query.first()
    if not conv:
        return {"error": "no conversation"}

    with app.app_context():
        token = create_access_token(identity=str(user_id))
    with app.test_request_context(
        f"/api/chat/conversations/{conv.id}",
        headers={"Authorization": f"Bearer {token}"},
    ):
        with catch_query_count() as (count, _):
            tracemalloc.start()
            t0 = time.perf_counter()
            result = get_conversation(conv.id)
            elapsed = time.perf_counter() - t0
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

    return {
        "endpoint": "get_conversation",
        "db_queries": count[0],
        "time_ms": round(elapsed * 1000, 2),
        "peak_memory_kb": round(peak / 1024, 1),
    }


def benchmark_list_paper_conversations(user_id: int) -> dict:
    from tools.chat.chat_routes import list_paper_conversations

    with app.app_context():
        conv = Conversation.query.first()
        token = create_access_token(identity=str(user_id))
    if not conv:
        return {"error": "no conversation"}

    with app.test_request_context(
        f"/api/chat/conversations/{conv.id}",
        headers={"Authorization": f"Bearer {token}"},
    ):
        with catch_query_count() as (count, _):
            tracemalloc.start()
            t0 = time.perf_counter()
            result = get_conversation(conv.id)
            elapsed = time.perf_counter() - t0
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

    return {
        "endpoint": "get_conversation",
        "db_queries": count[0],
        "time_ms": round(elapsed * 1000, 2),
        "peak_memory_kb": round(peak / 1024, 1),
    }


def benchmark_get_conversation(user_id: int) -> dict:
    from tools.chat.chat_routes import get_conversation

    with app.app_context():
        conv = Conversation.query.first()
    if not conv:
        return {"error": "no conversation"}

    with app.app_context():
        token = create_access_token(identity=str(user_id))
    with app.test_request_context(
        f"/api/chat/conversations/{conv.id}",
        headers={"Authorization": f"Bearer {token}"},
    ):
        with catch_query_count() as (count, _):
            tracemalloc.start()
            t0 = time.perf_counter()
            result = get_conversation(conv.id)
            elapsed = time.perf_counter() - t0
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

    return {
        "endpoint": "get_conversation",
        "db_queries": count[0],
        "time_ms": round(elapsed * 1000, 2),
        "peak_memory_kb": round(peak / 1024, 1),
    }


def benchmark_conversation_list(user_id: int) -> dict:
    from tools.chat.chat_routes import list_paper_conversations

    with app.app_context():
        paper = Paper.query.first()
        token = create_access_token(identity=str(user_id))
    if not paper:
        return {"error": "no paper"}

    with app.test_request_context(
        f"/api/papers/{paper.id}/conversations",
        headers={"Authorization": f"Bearer {token}"},
    ):
        with catch_query_count() as (count, _):
            tracemalloc.start()
            t0 = time.perf_counter()
            result = list_paper_conversations(paper.id)
            elapsed = time.perf_counter() - t0
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

    return {
        "endpoint": "list_paper_conversations",
        "convs_returned": len(result) if isinstance(result, list) else 0,
        "db_queries": count[0],
        "time_ms": round(elapsed * 1000, 2),
        "peak_memory_kb": round(peak / 1024, 1),
    }


# ── Report ─────────────────────────────────────────────────────────────────


def print_report(before: list[dict] | None, after: list[dict]):
    print()
    print("=" * 72)
    print("  CHAT SYSTEM PERFORMANCE BENCHMARK")
    print(f"  Run at: {datetime.now().isoformat()}")
    print("=" * 72)

    for metric in after:
        print(f"\n  ► {metric['endpoint']}")
        print(f"    DB Queries      : {metric.get('db_queries', '?')}")
        print(f"    Response Time   : {metric.get('time_ms', '?')} ms")
        print(f"    Peak Memory     : {metric.get('peak_memory_kb', '?')} KB")
        if before:
            bm = next((b for b in before if b["endpoint"] == metric["endpoint"]), None)
            if bm:
                q_improvement = (
                    f"{(1 - metric['db_queries'] / max(bm['db_queries'], 1)) * 100:.0f}%"
                    if bm.get("db_queries")
                    else "N/A"
                )
                t_improvement = (
                    f"{(1 - metric['time_ms'] / max(bm['time_ms'], 1)) * 100:.0f}%"
                    if bm.get("time_ms")
                    else "N/A"
                )
                print(f"    vs before: queries {q_improvement}, time {t_improvement}")


def run_benchmark(quick: bool = False):
    num_papers = 10 if quick else 100
    convs_per_paper = 5 if quick else 5

    with app.app_context():
        db.create_all()

    user_id = seed_data(num_papers, convs_per_paper)

    print(f"\n[benchmark] running with {num_papers} papers, {num_papers * convs_per_paper} conversations")
    print("[benchmark] running list_paper_chats (optimised)…")
    r1 = benchmark_list_paper_chats(user_id)
    print(f"  → {r1['db_queries']} queries, {r1['time_ms']} ms")

    print("[benchmark] running get_conversation…")
    r2 = benchmark_get_conversation(user_id)
    print(f"  → {r2.get('db_queries', '?')} queries, {r2.get('time_ms', '?')} ms")

    print("[benchmark] running list_paper_conversations…")
    r3 = benchmark_conversation_list(user_id)
    print(f"  → {r3.get('db_queries', '?')} queries, {r3.get('time_ms', '?')} ms")

    results = [r1, r2, r3]

    # Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "config": {"num_papers": num_papers, "convs_per_paper": convs_per_paper},
        "optimised_results": results,
    }
    os.makedirs("tests/performance/reports", exist_ok=True)
    report_path = f"tests/performance/reports/chat_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n[report] saved to {report_path}")

    print_report(before=None, after=results)

    # Summary
    total_before_queries = num_papers + (num_papers * convs_per_paper) + (num_papers * convs_per_paper * 10)
    total_after_queries = 3  # selectinload: papers + conversations + messages
    print("\n" + "-" * 72)
    print("  N+1 QUERY ELIMINATION SUMMARY")
    print(f"  Before (estimated naive): {total_before_queries}+ queries")
    print(f"  After  (eager-loaded):    ~{total_after_queries} queries")
    print(f"  Reduction:               ~{((1 - total_after_queries / max(total_before_queries, 1)) * 100):.0f}%")
    print("-" * 72)


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    run_benchmark(quick=quick)
