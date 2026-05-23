"""
Workflow Tool Integration
=========================
Integrates workflow_engine with chat system.
"""

import json
from database.models import ProjectMemory, db
from workflows.engine import (
    get_phase_questions,
    get_next_phase,
    validate_workflow,
    WORKFLOW_PHASES
)


def start_workflow(paper_id, user_id):
    """
    Start or continue the workflow for a paper.
    
    Returns:
        dict: multi_question proposal with current phase questions
    """
    workflow_state = _get_workflow_state(paper_id, user_id)
    
    current_phase = workflow_state.get("current_phase", "0")
    answers = workflow_state.get("answers", {})
    
    questions = get_phase_questions(current_phase, answers)
    
    if not questions:
        return {
            "kind": "multi_question",
            "phase": current_phase,
            "phase_name": WORKFLOW_PHASES.get(current_phase, {}).get("name", ""),
            "questions": [],
            "message": "Workflow selesai! Semua fase telah dijawab."
        }
    
    formatted_questions = []
    for q in questions:
        formatted_questions.append({
            "key": q["key"],
            "label": q["question"],
            "options": q.get("options", [])
        })
    
    return {
        "kind": "multi_question",
        "phase": current_phase,
        "phase_name": WORKFLOW_PHASES.get(current_phase, {}).get("name", ""),
        "description": WORKFLOW_PHASES.get(current_phase, {}).get("description", ""),
        "questions": formatted_questions,
        "total_phases": 10
    }


def save_workflow_answers(paper_id, user_id, phase, answers_list):
    """
    Save workflow answers and advance to next phase.
    
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
    for answer in answers_list:
        all_answers[answer["key"]] = answer["value"]
    
    next_phase = get_next_phase(phase, all_answers)
    
    if next_phase == "9":
        validation = validate_workflow(all_answers)
        _save_workflow_state(paper_id, user_id, next_phase, all_answers)
        
        return {
            "kind": "workflow_validation",
            "validation": validation,
            "message": "Workflow selesai! Berikut ringkasan dan validasi."
        }
    
    if next_phase:
        _save_workflow_state(paper_id, user_id, next_phase, all_answers)
        return {
            "kind": "workflow_continue",
            "next_phase": next_phase,
            "message": f"Jawaban disimpan. Lanjut ke fase {next_phase}."
        }
    
    _save_workflow_state(paper_id, user_id, "completed", all_answers)
    return {
        "kind": "workflow_complete",
        "message": "Workflow selesai! Semua informasi telah dikumpulkan."
    }


def _get_workflow_state(paper_id, user_id):
    """Get workflow state from ProjectMemory."""
    mem = ProjectMemory.query.filter_by(
        paper_id=paper_id,
        user_id=user_id,
        key="workflow_state"
    ).first()
    
    if not mem:
        return {"current_phase": "0", "answers": {}}
    
    try:
        return json.loads(mem.value)
    except:
        return {"current_phase": "0", "answers": {}}


def _save_workflow_state(paper_id, user_id, phase, answers):
    """Save workflow state to ProjectMemory."""
    state = {
        "current_phase": phase,
        "answers": answers
    }
    
    mem = ProjectMemory.query.filter_by(
        paper_id=paper_id,
        user_id=user_id,
        key="workflow_state"
    ).first()
    
    if mem:
        mem.value = json.dumps(state, ensure_ascii=False)
    else:
        mem = ProjectMemory(
            paper_id=paper_id,
            user_id=user_id,
            key="workflow_state",
            value=json.dumps(state, ensure_ascii=False),
            kind="workflow"
        )
        db.session.add(mem)
    
    db.session.commit()
