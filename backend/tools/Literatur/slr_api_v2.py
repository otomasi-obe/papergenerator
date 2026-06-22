"""SLR v2 API — Active Learning Screening endpoints.

Register via: from tools.Literatur.slr_api_v2 import register_slr_v2; register_slr_v2(slr_api)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import numpy as np
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from database.models import LiteratureItem, SlrJob, db, safe_commit

from .slr.dedup import Deduplicator, normalize_title
from .slr.screening import ActiveScreener, ScreeningResult, ScreeningState

log = logging.getLogger(__name__)

slr_v2_bp = Blueprint("slr_v2", __name__)

# In-memory screening sessions (per paper_id — bisa dipindah ke Redis kalau perlu)
_sessions: dict[str, ActiveScreener] = {}
_states: dict[str, ScreeningState] = {}
_results: dict[str, ScreeningResult] = {}


def _paper_key(paper_id: str, job_id: str | None = None) -> str:
    return f"{paper_id}:{job_id or 'default'}"


def register_slr_v2() -> Blueprint:
    """Register semua SLR v2 endpoints. Dipanggil dari main.py sebelum register_blueprint."""

    @slr_v2_bp.post("/api/papers/<paper_id>/slr/screening/init")
    @jwt_required()
    def slr_screening_init(paper_id: str):
        """Inisialisasi active learning screening.

        Body:
        {
            "paper_ids": ["id1", ...],    # IDs dari hasil SLR fetch
            "titles": ["title1", ...],
            "abstracts": ["abstract1", ...],
            "seed_included": [0, 5],       # indeks seed paper yang sudah relevant
            "target_recall": 0.95,
            "job_id": "slr_abc123"         # optional — hubungkan ke SlrJob
        }
        """
        user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}

        paper_ids = data.get("paper_ids", [])
        titles = data.get("titles", [])
        abstracts = data.get("abstracts", [])
        seed_included = data.get("seed_included", [])
        target_recall = float(data.get("target_recall", 0.95))
        job_id = data.get("job_id")

        n = len(paper_ids)
        if n == 0:
            return jsonify({"error": "No papers provided"}), 400
        if len(titles) != n or len(abstracts) != n:
            return jsonify({"error": "Mismatched arrays"}), 400

        key = _paper_key(paper_id, job_id)
        screener = ActiveScreener(target_recall=target_recall)
        state = screener.initialize(paper_ids, titles, abstracts,
                                     seed_included=seed_included)
        _sessions[key] = screener
        _states[key] = state

        return jsonify({
            "status": "initialized",
            "n_total": state.n_total,
            "n_seed": len(state.screened_idx),
            "n_unscreened": len(state.unscreened_idx),
            "paper_id": paper_id,
            "key": key,
        })

    @slr_v2_bp.get("/api/papers/<paper_id>/slr/screening/next")
    @jwt_required()
    def slr_screening_next(paper_id: str):
        """Dapatkan paper berikutnya yang harus discreen (certainty sampling).

        Query params:
            job_id: optional SlrJob ID

        Returns:
        {
            "index": 12,
            "paper_id": "abc",
            "title": "...",
            "abstract": "...",
            "model_probability": 0.62,
            "n_remaining": 250,
            "stop_check": {"should_stop": false, "reason": ""}
        }
        """
        job_id = request.args.get("job_id")
        key = _paper_key(paper_id, job_id)

        screener = _sessions.get(key)
        if not screener:
            return jsonify({"error": "No active screening session"}), 404

        next_idx = screener.next_to_screen()
        if next_idx is None:
            return jsonify({"done": True, "message": "All papers screened"})

        # Get model probability
        scores = screener.get_scores()
        proba = scores.get(next_idx, 0.5)

        # Check stop
        should_stop, reason = screener.check_stop()

        return jsonify({
            "index": next_idx,
            "paper_id": screener.state.paper_ids[next_idx],
            "title": screener.state.titles[next_idx],
            "abstract": screener.state.abstracts[next_idx][:1000],
            "model_probability": round(proba, 4),
            "n_remaining": len(screener.state.unscreened_idx) - 1,
            "n_screened": screener.state.n_screened,
            "stop_check": {"should_stop": should_stop, "reason": reason},
        })

    @slr_v2_bp.post("/api/papers/<paper_id>/slr/screening/label")
    @jwt_required()
    def slr_screening_label(paper_id: str):
        """Beri label pada paper yang baru discreen.

        Body:
        {
            "index": 12,
            "is_relevant": true,
            "job_id": "slr_abc123"
        }
        """
        data = request.get_json(silent=True) or {}
        idx = data.get("index")
        is_relevant = data.get("is_relevant")
        job_id = data.get("job_id")
        key = _paper_key(paper_id, job_id)

        if idx is None or is_relevant is None:
            return jsonify({"error": "index and is_relevant required"}), 400

        screener = _sessions.get(key)
        if not screener:
            return jsonify({"error": "No active screening session"}), 404

        screener.label(int(idx), bool(is_relevant))

        return jsonify({
            "status": "labeled",
            "index": int(idx),
            "is_relevant": bool(is_relevant),
            "n_screened": screener.state.n_screened,
            "n_relevant": screener.state.n_relevant_found,
            "consecutive_irrelevant": screener.state.consecutive_irrelevant,
            "recall_estimate": round(
                screener.state.recall_estimates[-1], 4
            ) if screener.state.recall_estimates else None,
        })

    @slr_v2_bp.post("/api/papers/<paper_id>/slr/screening/batch-label")
    @jwt_required()
    def slr_screening_batch_label(paper_id: str):
        """Batch labeling.

        Body:
        {
            "labels": [[12, true], [15, false], [18, true]],
            "job_id": "slr_abc123"
        }
        """
        data = request.get_json(silent=True) or {}
        labels_data = data.get("labels", [])
        job_id = data.get("job_id")
        key = _paper_key(paper_id, job_id)

        screener = _sessions.get(key)
        if not screener:
            return jsonify({"error": "No active screening session"}), 404

        for idx, is_rel in labels_data:
            screener.label(int(idx), bool(is_rel))

        should_stop, reason = screener.check_stop()

        return jsonify({
            "status": "batch_labeled",
            "n_labeled": len(labels_data),
            "n_screened": screener.state.n_screened,
            "n_relevant": screener.state.n_relevant_found,
            "stop_check": {"should_stop": should_stop, "reason": reason},
        })

    @slr_v2_bp.post("/api/papers/<paper_id>/slr/screening/finalize")
    @jwt_required()
    def slr_screening_finalize(paper_id: str):
        """Finalisasi screening — hitung metrik dan simpan hasil.

        Body:
        {
            "job_id": "slr_abc123",
            "save_to_literature": true,    # simpan hasil ke literature_items
            "true_relevant_count": null    # optional, untuk validasi WSS@95
        }
        """
        user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        job_id = data.get("job_id")
        save_to_lit = data.get("save_to_literature", True)
        true_rel = data.get("true_relevant_count")
        key = _paper_key(paper_id, job_id)

        screener = _sessions.get(key)
        if not screener:
            return jsonify({"error": "No active screening session"}), 404

        result = screener.finalize(true_relevant_count=true_rel)
        _results[key] = result

        # Simpan ke LiteratureItem kalau diminta
        saved_count = 0
        if save_to_lit:
            try:
                for i, pid in enumerate(result.included_ids):
                    # Cek duplikat
                    existing = LiteratureItem.query.filter_by(
                        paper_id=paper_id,
                        title_norm=normalize_title(result.included_titles[i]),
                    ).first()
                    if existing:
                        continue

                    lit = LiteratureItem(
                        paper_id=paper_id,
                        user_id=user_id,
                        source_kind="slr",
                        source="slr_active_learning",
                        title=result.included_titles[i],
                        title_norm=normalize_title(
                            result.included_titles[i]
                        ),
                        abstract=screener.state.abstracts[
                            screener.state.paper_ids.index(pid)
                        ] if pid in screener.state.paper_ids else "",
                        is_relevant=True,
                        is_checked=False,
                        must_read=False,
                        slr_job_id=job_id,
                    )
                    db.session.add(lit)
                    saved_count += 1

                safe_commit()
                log.info("Saved %d included papers to literature_items", saved_count)
            except Exception as e:
                db.session.rollback()
                log.exception("Failed to save screening results: %s", e)

        # Update SlrJob result kalau ada job_id
        if job_id:
            try:
                job = SlrJob.query.filter_by(id=job_id).first()
                if job:
                    job.result = {
                        **(job.result or {}),
                        "screening": result.to_dict(),
                    }
                    safe_commit()
            except Exception:
                db.session.rollback()

        # Cleanup session
        _sessions.pop(key, None)
        _states.pop(key, None)

        return jsonify({
            "status": "finalized",
            "screening_result": result.to_dict(),
            "saved_to_literature": saved_count,
        })

    @slr_v2_bp.post("/api/papers/<paper_id>/slr/screening/dedup")
    @jwt_required()
    def slr_screening_dedup(paper_id: str):
        """Deduplikasi paper pool sebelum screening.

        Body:
        {
            "papers": [{"id": "...", "doi": "...", "title": "..."}, ...]
        }
        """
        data = request.get_json(silent=True) or {}
        papers = data.get("papers", [])

        dedup = Deduplicator()
        unique, duplicates = dedup.deduplicate(papers)

        return jsonify({
            "n_input": len(papers),
            "n_unique": len(unique),
            "n_duplicates": len(duplicates),
            "unique": unique,
            "duplicates": [{"id": d.get("id"), "reason": d.get("_dup_reason")}
                           for d in duplicates],
        })

    @slr_v2_bp.get("/api/papers/<paper_id>/slr/screening/status")
    @jwt_required()
    def slr_screening_status(paper_id: str):
        """Status screening saat ini."""
        job_id = request.args.get("job_id")
        key = _paper_key(paper_id, job_id)

        screener = _sessions.get(key)
        result = _results.get(key)

        if result:
            return jsonify({
                "status": "completed",
                "result": result.to_dict(),
            })

        if screener and screener.state:
            s = screener.state
            return jsonify({
                "status": "in_progress",
                "n_total": s.n_total,
                "n_screened": s.n_screened,
                "n_remaining": len(s.unscreened_idx),
                "n_relevant": s.n_relevant_found,
                "n_irrelevant": s.n_irrelevant_found,
                "consecutive_irrelevant": s.consecutive_irrelevant,
                "stopped": s.stopped,
                "stop_reason": s.stop_reason,
            })

        return jsonify({"status": "not_started"})

    @slr_v2_bp.post("/api/papers/<paper_id>/slr/screening/reset")
    @jwt_required()
    def slr_screening_reset(paper_id: str):
        """Reset screening session."""
        job_id = request.args.get("job_id")
        key = _paper_key(paper_id, job_id)

        _sessions.pop(key, None)
        _states.pop(key, None)
        _results.pop(key, None)
        return jsonify({"status": "reset"})

    return slr_v2_bp