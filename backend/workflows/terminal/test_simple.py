#!/usr/bin/env python3
"""
Simple test to verify workflow stores full text.
"""

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from workflows.engine import WORKFLOW_PHASES, get_phase_questions, get_next_phase, validate_workflow

# Simulate WorkflowState from run_conv.py
class WorkflowState:
    def __init__(self):
        self.phase = "0"
        self.answers = {}
    
    def _resolve_answer_text(self, question_key, answer_value):
        """Resolve full text from answer value."""
        phase_def = WORKFLOW_PHASES.get(self.phase, {})
        
        questions = phase_def.get("questions", [])
        for q in questions:
            if q.get("key") == question_key:
                options = q.get("options", [])
                for opt in options:
                    if opt.get("value") == answer_value:
                        return opt.get("label", answer_value)
                return answer_value
        
        return answer_value
    
    def save_answers(self, raw_answers):
        """Save answers with full text resolution."""
        if isinstance(raw_answers, list):
            for item in raw_answers:
                key = item["key"]
                value = item["value"]
                full_text = self._resolve_answer_text(key, value)
                self.answers[key] = full_text
                print(f"  {key}: '{value}' → '{full_text}'")
        else:
            for key, value in raw_answers.items():
                full_text = self._resolve_answer_text(key, value)
                self.answers[key] = full_text
                print(f"  {key}: '{value}' → '{full_text}'")
        
        self.phase = get_next_phase(self.phase, self.answers) or "done"

def main():
    print("=" * 70)
    print("SIMPLE WORKFLOW TEST - Full Text Storage")
    print("=" * 70)
    
    wf = WorkflowState()
    
    # Phase 0
    print("\n[Phase 0] Pre-Questionnaire")
    print("-" * 70)
    phase_0_answers = [
        {"key": "progress_level", "value": "A"},
        {"key": "data_readiness", "value": "D"},
        {"key": "team_size", "value": "A"},
    ]
    wf.save_answers(phase_0_answers)
    print(f"Next phase: {wf.phase}")
    
    # Phase 1
    print("\n[Phase 1] Profil Dasar Paper")
    print("-" * 70)
    phase_1_answers = [
        {"key": "field", "value": "B"},
        {"key": "paper_type", "value": "B"},
        {"key": "target_publication", "value": "A"},
        {"key": "title", "value": "Analisis Struktur Jembatan dengan Material Daur Ulang"},
    ]
    wf.save_answers(phase_1_answers)
    print(f"Next phase: {wf.phase}")
    
    # Show final state
    print("\n" + "=" * 70)
    print("FINAL WORKFLOW STATE")
    print("=" * 70)
    print(json.dumps(wf.answers, indent=2, ensure_ascii=False))
    
    # Verify no letter codes
    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)
    letter_codes = ["A", "B", "C", "D"]
    has_letter_codes = False
    for key, value in wf.answers.items():
        if value in letter_codes:
            print(f"✗ {key}: '{value}' (still a letter code!)")
            has_letter_codes = True
    
    if not has_letter_codes:
        print("✓ SUCCESS: All answers stored as full text")
    else:
        print("✗ FAILED: Some answers still stored as letter codes")
    
    print("=" * 70 + "\n")
    
    return 0 if not has_letter_codes else 1

if __name__ == "__main__":
    sys.exit(main())
