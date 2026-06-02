"""
Workflow blueprint — offline onboarding questions.

The chat empty-state "Buat baru" path needs to render the static identity
questions (Phase 0 + Phase 1 profile) INSTANTLY, without an AI round-trip.
This endpoint returns that offline onboarding batch (fixed options, with a
recommended default pre-selected) and persists the fresh workflow state so the
subsequent answer submission flows into the normal dynamic (AI) phases.
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from database.models import Paper

log = logging.getLogger(__name__)

workflow_bp = Blueprint("workflow", __name__, url_prefix="/api/papers")


@workflow_bp.route("/<paper_id>/workflow/onboarding", methods=["POST"])
@jwt_required()
def start_onboarding(paper_id):
    """Return the offline onboarding questions for a fresh workflow start.

    No AI is invoked: the questions are static templates with recommended
    answers pre-selected. Workflow state is initialised so the user's answers
    (submitted via the normal chat flow) advance into the dynamic phases.
    """
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404

    # Imported lazily to keep the blueprint import light and avoid circulars.
    from workflows.tool import start_workflow

    try:
        result = start_workflow(paper_id, user_id)
    except Exception:
        log.exception("start_onboarding failed for paper=%s", paper_id)
        return jsonify({"error": "Failed to start workflow"}), 500

    return jsonify(result)
