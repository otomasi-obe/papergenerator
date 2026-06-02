#!/usr/bin/env python3
"""
Deterministic end-to-end driver for the full 9-phase workflow.

Drives run_conv.WorkflowState directly (no LLM chat loop) using scenario 30's
answer turns from ContohQuestion2, then prints the final workflow_state answers
to prove every value is full text (no bare A/B/C/D).

AI option generation is patched to the offline fallback options so the run is
deterministic and network-free — the point of this test is the answer storage
mapping, not AI option quality.
"""

import json
import re
import sys
from pathlib import Path

TERMINAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TERMINAL_DIR))

import run_conv
from run_conv import WorkflowState, SCENARIOS, _load_be


def main():
    be = _load_be()

    # ── Patch AI option generation → offline fallback (no network) ──────────
    import workflows.engine as engine

    def _offline_ai_options(question, previous_answers):
        return engine._get_fallback_options(
            question["id"], question["key"], previous_answers
        )

    engine.generate_ai_options = _offline_ai_options

    wf = WorkflowState(be)

    # Scenario 30 = full 9-phase workflow. Skip the first greeting turn.
    scenario = SCENARIOS[29]
    turns = list(scenario["turns"][1:])  # drop greeting

    wf.start()  # builds phase-0 questions + option snapshot

    cursor = 0
    for phase in ["0", "1", "2", "3", "4", "5", "6", "7", "8"]:
        wf.phase = phase
        # Build the multi-question (also snapshots presented options) ONCE.
        mq = wf._build_multi_q(phase)
        keys = [q["key"] for q in mq["questions"]]
        n = len(keys)

        chunk = turns[cursor:cursor + n]
        cursor += n
        if len(chunk) < n:
            print(f"[WARN] phase {phase}: expected {n} answers, got {len(chunk)}")

        answers_list = [{"key": k, "value": v} for k, v in zip(keys, chunk)]
        print(f"\n── Phase {phase} ({be['WORKFLOW_PHASES'][phase]['name']}) ──")
        for a in answers_list:
            print(f"   {a['key']:22s} <= {a['value']!r}")

        out = wf.save_answers(answers_list)
        if "workflow_complete_generating" in out:
            print("\n[workflow completed → generation triggered]")
            break

    print("\n" + "=" * 60)
    print("FINAL workflow_state answers (must be full text):")
    print("=" * 60)
    print(json.dumps(wf.answers, ensure_ascii=False, indent=2))

    # Validation: no value should be a bare single-letter option code.
    bad = {k: v for k, v in wf.answers.items()
           if isinstance(v, str) and re.fullmatch(r"[A-E]", v.strip())}
    print("\n" + "=" * 60)
    if bad:
        print(f"✗ FAIL: {len(bad)} value(s) still stored as letter code: {bad}")
        return 1
    print(f"✓ PASS: all {len(wf.answers)} answers stored as full text "
          f"(0 bare letter codes)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
