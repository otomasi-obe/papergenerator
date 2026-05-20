# ADR-002: Background AI Jobs — Threads + DB-backed State (no Celery)

**Status:** Accepted (2026-05-20)

## Context
`/api/generate-full` produces a paper that takes 60–600 s of upstream LLM
calls. Synchronous HTTP would exceed gunicorn's 120 s timeout and tie up
worker threads.

## Decision
Run generation in an in-process daemon thread, persist state in `ai_jobs`
(PostgreSQL), expose `GET /api/job/<id>` for polling.

Add a sweeper thread that marks jobs stuck in `pending > 15min` as
`error+timeout=True`. Bounded — does not require Celery, Redis, or external
queues at current scale.

## Alternatives Considered
- **Celery + Redis** — robust retry, cross-host, observable. Added moving parts
  unnecessary for a single-VPS deployment with <10 generate-full/min.
- **RQ** — same trade-off, simpler than Celery. Re-evaluate at scale.
- **In-memory dict (original)** — lost on worker restart; replaced by DB.

## Re-evaluation triggers
- > 100 generate-full/min sustained
- Need to scale beyond single host (multi-region or HA)
- Need explicit retry/DLQ semantics
