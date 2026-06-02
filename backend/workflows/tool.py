"""
Workflow Tool Integration
=========================
Integrates workflow_engine with chat system.
"""

import json
import logging
import os
import requests

from database.models import ProjectMemory, db
from workflows.engine import (
    STATIC_OPTION_KEYS,
    WORKFLOW_PHASES,
    get_next_phase,
    get_offline_onboarding_questions,
    get_phase_questions,
    resolve_static_label,
    validate_workflow,
)

log = logging.getLogger(__name__)


def _snapshot_options(formatted_questions):
    """Build a {question_key: {value: label}} map from presented questions.

    Only AI-generated / dynamic options are captured. Static questions (fixed
    options defined in WORKFLOW_PHASES) are intentionally skipped: their labels
    can always be resolved offline via :func:`resolve_static_label`, so storing
    them would only bloat the persisted state (and, in turn, the AI context).
    """
    snapshot = {}
    for q in formatted_questions:
        key = q.get("key")
        if not key or key in STATIC_OPTION_KEYS:
            continue
        opt_map = {}
        for opt in q.get("options", []) or []:
            val = opt.get("value")
            label = opt.get("label")
            if val is not None and label is not None:
                opt_map[str(val)] = label
        if opt_map:
            snapshot[key] = opt_map
    return snapshot


def _generate_phase2_suggestions(answers: dict) -> dict | None:
    """Generate AI-powered topic suggestions for Phase 2 based on user profile.

    Called when transitioning to Phase 2 ("Topik & Research Gap"). Uses the
    collected identity data (field, paper_type, target_publication, title) to
    produce 4 specific, relevant topic suggestions — plus matching problem
    statements and research gaps — so the user sees tailored options immediately
    instead of waiting for a full LLM discovery round-trip.

    Returns a dict {question_key: [{value, label}, ...]} keyed by
    "topic" / "problem_statement" / "research_gap", or None on failure.
    """
    base_url = (os.getenv("AIOTOMASI_API") or "").rstrip("/")
    api_key = os.getenv("AIOTOMASI_APIKEY") or ""
    model = os.getenv("MODELCHAT") or "VIOLA-CHAT"
    if not (base_url and api_key):
        log.warning("_generate_phase2_suggestions: AIOTOMASI_API/APIKEY not set")
        return None

    field = (answers.get("field") or "").strip()
    paper_type = (answers.get("paper_type") or "").strip()
    target = (answers.get("target_publication") or "").strip()
    title = (answers.get("title") or "").strip()

    # Build a compact profile paragraph so the AI can ground its suggestions.
    profile_parts = []
    if field:
        profile_parts.append(f"Bidang ilmu: {field}")
    if paper_type:
        profile_parts.append(f"Jenis paper: {paper_type}")
    if target:
        profile_parts.append(f"Target publikasi: {target}")
    if title:
        profile_parts.append(f"Judul provisional: {title}")
    profile_text = "\n".join(profile_parts) if profile_parts else "Tidak ada profil."

    sys_prompt = (
        "You are an academic research advisor helping a student narrow down "
        "their paper topic. Based on the student's profile, suggest 4 specific, "
        "actionable research topics — each paired with a matching problem "
        "statement and research gap. Output ONLY valid JSON (no markdown, no "
        "explanations) in this exact structure:\n"
        '{"topics":[{"topic":"...","problem":"...","gap":"..."},...]}\n'
        "Rules:\n"
        "- Exactly 4 entries.\n"
        "- Each topic must be specific and researchable (not generic like "
        '"Studi tentang X").\n'
        "- Problem statement: one sentence describing the core issue.\n"
        "- Research gap: one sentence identifying what has not been answered.\n"
        "- All in Bahasa Indonesia (formal akademik).\n"
        "- Max 80 chars per field.\n"
        "- Topics must be DISTINCT from each other."
    )

    user_prompt = (
        f"## Profil Mahasiswa\n{profile_text}\n\n"
        "Berikan 4 rekomendasi topik riset spesifik beserta problem statement "
        "dan research gap dalam format JSON."
    )

    try:
        resp = requests.post(
            base_url + "/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "max_tokens": 2000,
                "temperature": 0.7,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            log.warning(f"_generate_phase2_suggestions: API returned {resp.status_code}")
            return None

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return None

        content = (choices[0].get("message", {}).get("content") or "").strip()
        # Strip markdown code fences if present.
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        parsed = json.loads(content)
        topics_list = parsed.get("topics") or []
        if not topics_list:
            return None

        topic_opts = []
        problem_opts = []
        gap_opts = []
        for i, t in enumerate(topics_list[:4]):
            label = chr(ord("A") + i)  # A, B, C, D
            t_text = (t.get("topic") or "").strip()
            p_text = (t.get("problem") or "").strip()
            g_text = (t.get("gap") or "").strip()
            if t_text:
                topic_opts.append({"value": label, "label": t_text})
            if p_text:
                problem_opts.append({"value": label, "label": p_text})
            if g_text:
                gap_opts.append({"value": label, "label": g_text})

        suggestions = {}
        if topic_opts:
            suggestions["topic"] = topic_opts
        if problem_opts:
            suggestions["problem_statement"] = problem_opts
        if gap_opts:
            suggestions["research_gap"] = gap_opts

        return suggestions if suggestions else None

    except Exception:
        log.exception("_generate_phase2_suggestions failed")
        return None


def start_workflow(paper_id, user_id):
    """
    Start or continue the workflow for a paper.

    On a fresh start ("mulai dari 0") this serves ALL deterministic identity
    questions (Phase 0 status + Phase 1 static profile) as ONE offline batch.
    Those questions have fixed options, so no LLM call is needed to present
    them and nothing but the resolved data is persisted — keeping the workflow
    cheap on tokens. Dynamic (AI-generated) phases start only afterwards.

    Returns:
        dict: multi_question proposal with current phase questions
    """
    workflow_state = _get_workflow_state(paper_id, user_id)

    current_phase = workflow_state.get("current_phase", "0")
    answers = workflow_state.get("answers", {})

    # Fresh start: collect the static identity data offline in one shot.
    onboarding_keys = {
        "progress_level", "data_readiness", "team_size",
        "field", "paper_type", "target_publication",
    }
    if current_phase == "0" and not (onboarding_keys & set(answers)):
        questions = get_offline_onboarding_questions()
        formatted_questions = []
        for q in questions:
            qid = q.get("id", "")
            label = f"[{qid}] {q['question']}" if qid else q["question"]
            formatted_questions.append(
                {"id": qid, "key": q["key"], "label": label, "options": q.get("options", [])}
            )
        # All options are static → resolvable offline, so store NO snapshot.
        _save_workflow_state(paper_id, user_id, "0", answers, pending_options={})
        return {
            "kind": "multi_question",
            "phase": "0",
            "phase_name": "Data Awal",
            "description": "Lengkapi data dasar paper kamu (otomatis, tanpa AI).",
            "questions": formatted_questions,
            "total_phases": 10,
            "onboarding": True,
        }

    # Continuing: present this phase's questions, skipping any already answered
    # offline (e.g. Phase 1's static fields collected during onboarding).
    questions = [
        q for q in get_phase_questions(current_phase, answers)
        if q.get("key") not in answers
    ]

    if not questions:
        return {
            "kind": "multi_question",
            "phase": current_phase,
            "phase_name": WORKFLOW_PHASES.get(current_phase, {}).get("name", ""),
            "questions": [],
            "message": "Workflow selesai! Semua fase telah dijawab.",
        }

    formatted_questions = []
    for q in questions:
        qid = q.get("id", "")
        label = f"[{qid}] {q['question']}" if qid else q["question"]
        formatted_questions.append(
            {"id": qid, "key": q["key"], "label": label, "options": q.get("options", [])}
        )

    # Phase 2 (Topik & Research Gap): pre-generate AI topic suggestions from
    # the user's onboarding profile so the card arrives with relevant options
    # already populated — no extra LLM round-trip needed.
    if current_phase == "2":
        suggestions = _generate_phase2_suggestions(answers)
        if suggestions:
            for fq in formatted_questions:
                key = fq.get("key")
                if key and key in suggestions:
                    fq["options"] = suggestions[key]
            log.info(
                "start_workflow: injected phase-2 suggestions for keys=%s",
                list(suggestions),
            )

    # Drop ai_generated questions that still have no options after suggestion
    # injection. They'll be handled conversationally by the LLM via AskQuestions
    # instead of being rendered as a card with empty choices.
    formatted_questions = [
        fq for fq in formatted_questions
        if not (fq.get("options") is None or len(fq.get("options") or []) == 0)
    ]

    if not formatted_questions:
        return {
            "kind": "multi_question",
            "phase": current_phase,
            "phase_name": WORKFLOW_PHASES.get(current_phase, {}).get("name", ""),
            "questions": [],
            "message": "Semua pertanyaan fase ini akan dipandu oleh AI.",
        }

    # Persist ONLY the dynamic (AI-generated) options being presented so that,
    # when the user answers with A/B/C/D, we can resolve their full label text.
    # Static options are skipped (resolved offline) to keep the state small.
    pending_options = _snapshot_options(formatted_questions)
    _save_workflow_state(
        paper_id, user_id, current_phase, answers, pending_options=pending_options
    )

    return {
        "kind": "multi_question",
        "phase": current_phase,
        "phase_name": WORKFLOW_PHASES.get(current_phase, {}).get("name", ""),
        "description": WORKFLOW_PHASES.get(current_phase, {}).get("description", ""),
        "questions": formatted_questions,
        "total_phases": 10,
    }


def _resolve_answer_text(phase, question_key, answer_value, pending_options=None):
    """
    Resolve the full text of an answer from its value code.

    Resolution order:
        1. pending_options snapshot (the exact options presented to the user,
           including AI-generated ones) — authoritative.
        2. Static WORKFLOW_PHASES definition (main questions + branches).
        3. Raw input returned as-is (custom / free-text answer).

    Args:
        phase: Current phase (e.g., "0", "1", "2")
        question_key: Question key (e.g., "progress_level", "data_readiness")
        answer_value: Answer value (e.g., "A", "B", "C", "D" or custom text)
        pending_options: Optional {key: {value: label}} snapshot of presented
            options for this phase.

    Returns:
        str: Full text of the answer (option label or custom text)
    """
    # Only attempt code→label resolution for short option codes (A-E etc.).
    # Anything else is already free text and must be preserved verbatim.
    value_str = answer_value if isinstance(answer_value, str) else str(answer_value)

    # 1) Snapshot of exactly what was presented (handles AI-generated options).
    if pending_options:
        opt_map = pending_options.get(question_key)
        if opt_map and value_str in opt_map:
            return opt_map[value_str]

    # 2) Static phase definition (main questions).
    phase_def = WORKFLOW_PHASES.get(phase, {})
    questions = phase_def.get("questions", [])
    for q in questions:
        if q.get("key") == question_key:
            for opt in q.get("options", []):
                if opt.get("value") == answer_value:
                    return opt.get("label", answer_value)
            return answer_value

    # 2b) Static phase definition (branches — phase 6 / conditional questions).
    branches = phase_def.get("branches", {})
    for branch_name, branch_def in branches.items():
        for q in branch_def.get("questions", []):
            if q.get("key") == question_key:
                for opt in q.get("options", []):
                    if opt.get("value") == answer_value:
                        return opt.get("label", answer_value)
                return answer_value

    # 2c) Cross-phase static lookup. The offline onboarding batch mixes Phase 0
    # status fields with Phase 1 profile fields in a single submission, so the
    # key may belong to a phase other than ``phase``. Scan every phase for a
    # static question matching this key.
    static_label = resolve_static_label(question_key, value_str)
    if static_label is not None:
        return static_label

    # 3) Not found anywhere → custom / free-text answer, keep as-is.
    return answer_value


def save_workflow_answers(paper_id, user_id, phase, answers_list):
    """
    Save workflow answers and advance to next phase.
    Stores the full text of answers instead of letter codes (A/B/C/D).

    Args:
        paper_id: Paper ID
        user_id: User ID
        phase: Current phase
        answers_list: List of {key, value} dicts

    Returns:
        dict: Result with next phase info or completion message
    """
    workflow_state = _get_workflow_state(paper_id, user_id)

    all_answers = workflow_state.get("answers", {})
    pending_options = workflow_state.get("pending_options", {})

    for answer in answers_list:
        answer_key = answer["key"]
        answer_value = answer["value"]
        full_text = _resolve_answer_text(
            phase, answer_key, answer_value, pending_options=pending_options
        )
        all_answers[answer_key] = full_text

    next_phase = get_next_phase(phase, all_answers)

    if next_phase == "9":
        validation = validate_workflow(all_answers)
        # Clear the stale option snapshot now that the phase is committed.
        _save_workflow_state(paper_id, user_id, next_phase, all_answers, pending_options={})

        return {
            "kind": "workflow_validation",
            "validation": validation,
            "message": "Workflow selesai! Berikut ringkasan dan validasi.",
        }

    if next_phase:
        _save_workflow_state(paper_id, user_id, next_phase, all_answers, pending_options={})
        return {
            "kind": "workflow_continue",
            "next_phase": next_phase,
            "message": f"Jawaban disimpan. Lanjut ke fase {next_phase}.",
        }

    _save_workflow_state(paper_id, user_id, "completed", all_answers, pending_options={})
    return {
        "kind": "workflow_complete",
        "message": "Workflow selesai! Semua informasi telah dikumpulkan.",
    }


def _get_workflow_state(paper_id, user_id):
    """Get workflow state from ProjectMemory."""
    mem = ProjectMemory.query.filter_by(
        paper_id=paper_id, user_id=user_id, key="workflow_state"
    ).first()

    if not mem:
        return {"current_phase": "0", "answers": {}, "pending_options": {}}

    try:
        state = json.loads(mem.value)
        state.setdefault("answers", {})
        state.setdefault("pending_options", {})
        return state
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        log.warning("Failed to parse workflow state: %s", e)
        return {"current_phase": "0", "answers": {}, "pending_options": {}}


def _save_workflow_state(paper_id, user_id, phase, answers, pending_options=None):
    """Save workflow state to ProjectMemory.

    ``pending_options`` is a {key: {value: label}} snapshot of the options that
    were last presented to the user. It is persisted so the next
    ``save_workflow_answers`` call can resolve A/B/C/D codes — including for
    AI-generated questions — to their full label text.
    """
    state = {
        "current_phase": phase,
        "answers": answers,
        "pending_options": pending_options or {},
    }

    mem = ProjectMemory.query.filter_by(
        paper_id=paper_id, user_id=user_id, key="workflow_state"
    ).first()

    if mem:
        mem.value = json.dumps(state, ensure_ascii=False)
    else:
        mem = ProjectMemory(
            paper_id=paper_id,
            user_id=user_id,
            key="workflow_state",
            value=json.dumps(state, ensure_ascii=False),
            kind="workflow",
        )
        db.session.add(mem)

    db.session.commit()


def jump_to_phase(paper_id, user_id, target_phase):
    """
    Jump to a specific phase for backward adjustment.

    Args:
        paper_id: Paper ID
        user_id: User ID
        target_phase: Phase to jump to (0-8)

    Returns:
        dict: Questions for the target phase
    """
    if target_phase not in WORKFLOW_PHASES:
        return {
            "kind": "error",
            "message": f"Invalid phase: {target_phase}",
        }

    workflow_state = _get_workflow_state(paper_id, user_id)
    answers = workflow_state.get("answers", {})

    # Get questions for target phase
    questions = get_phase_questions(target_phase, answers)

    if not questions:
        return {
            "kind": "error",
            "message": f"No questions found for phase {target_phase}",
        }

    formatted_questions = []
    for q in questions:
        qid = q.get("id", "")
        label = f"[{qid}] {q['question']}" if qid else q["question"]
        formatted_questions.append(
            {"id": qid, "key": q["key"], "label": label, "options": q.get("options", [])}
        )

    # Update current phase and snapshot the presented options for resolution.
    pending_options = _snapshot_options(formatted_questions)
    _save_workflow_state(
        paper_id, user_id, target_phase, answers, pending_options=pending_options
    )

    return {
        "kind": "multi_question",
        "phase": target_phase,
        "phase_name": WORKFLOW_PHASES.get(target_phase, {}).get("name", ""),
        "description": WORKFLOW_PHASES.get(target_phase, {}).get("description", ""),
        "questions": formatted_questions,
        "total_phases": 10,
        "is_backward_adjustment": True,
    }


def get_validation_with_phase_links(paper_id, user_id):
    """
    Get validation report with links to phases that need adjustment.

    Args:
        paper_id: Paper ID
        user_id: User ID

    Returns:
        dict: Validation report with phase links
    """
    workflow_state = _get_workflow_state(paper_id, user_id)
    answers = workflow_state.get("answers", {})

    validation = validate_workflow(answers)

    # Add phase links to warnings
    phase_mapping = {
        "RQ vs Metode": ["2", "3"],  # Phase 2 (RQ) and Phase 3 (Method)
        "Sampel vs Metode": ["3"],  # Phase 3 (Sample size and Method)
        "Sitasi vs Target": ["1", "5"],  # Phase 1 (Target) and Phase 5 (References)
        "Tone vs Target": ["1", "7"],  # Phase 1 (Target) and Phase 7 (Tone)
        "Etika vs Subjek": ["3"],  # Phase 3 (Ethics and Data source)
        "Anggaran vs Target": ["1", "8"],  # Phase 1 (Target) and Phase 8 (Budget)
        "Timeline vs Kompleksitas": ["4", "8"],  # Phase 4 (Complexity) and Phase 8 (Timeline)
    }

    for warning in validation.get("warnings", []):
        warning_type = warning.get("type", "")
        if warning_type in phase_mapping:
            warning["related_phases"] = phase_mapping[warning_type]
            warning["adjustment_actions"] = [
                {"label": "Kembali ke fase terkait", "action": "jump_to_phase", "phase": phase_mapping[warning_type][0]},
                {"label": "Terima warning & lanjut", "action": "accept_warning"},
                {"label": "Override (saya yakin)", "action": "override_warning"},
            ]

    return validation
