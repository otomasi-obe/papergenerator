#!/usr/bin/env python3
"""
Test snapshot-based answer resolution.

Validates the fix for AI-generated questions (phases 2-8) whose options are
NOT present in the static WORKFLOW_PHASES. Previously selecting "A" stored the
raw letter; now it resolves to the full label via the pending_options snapshot.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from workflows.tool import _resolve_answer_text, _snapshot_options


def test_snapshot_ai_generated():
    """AI-generated options (not in WORKFLOW_PHASES) resolve via snapshot."""
    print("=" * 60)
    print("Test: AI-generated question resolution via snapshot")
    print("=" * 60)

    # Simulate options presented for an AI-generated phase-2 question.
    formatted = [
        {
            "id": "2.1",
            "key": "topic",
            "label": "[2.1] Topik spesifik?",
            "options": [
                {"label": "Machine Learning untuk deteksi fraud", "value": "A"},
                {"label": "Optimasi rute logistik dengan GA", "value": "B"},
                {"label": "Analisis sentimen media sosial", "value": "C"},
                {"label": "Sistem rekomendasi hybrid", "value": "D"},
                {"label": "Ceritakan sendiri...", "value": "E"},
            ],
        }
    ]
    snapshot = _snapshot_options(formatted)

    cases = [
        ("2", "topic", "A", "Machine Learning untuk deteksi fraud"),
        ("2", "topic", "C", "Analisis sentimen media sosial"),
        ("2", "topic", "E", "Ceritakan sendiri..."),
        # Custom free text (no matching code) stays verbatim.
        ("2", "topic", "Jembatan cetak 3D dengan material daur ulang",
         "Jembatan cetak 3D dengan material daur ulang"),
    ]

    passed = failed = 0
    for phase, key, value, expected in cases:
        result = _resolve_answer_text(phase, key, value, pending_options=snapshot)
        ok = result == expected
        print(f"{'✓' if ok else '✗'} {key}: '{value}' → '{result}'"
              + ("" if ok else f" (expected '{expected}')"))
        passed += ok
        failed += (not ok)

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_static_still_works_without_snapshot():
    """Static phase-0/1 questions still resolve even with empty snapshot."""
    print("\n" + "=" * 60)
    print("Test: static resolution fallback (no snapshot)")
    print("=" * 60)

    cases = [
        ("0", "progress_level", "A", "Masih ide/konsep"),
        ("0", "data_readiness", "D", "Hasil final sudah siap"),
        ("5", "citation_style", "B", "IEEE (Teknik, CS)"),
        # phase-6 branch question
        ("6", "visualization_type", "A", "Tabel statistik deskriptif"),
    ]

    passed = failed = 0
    for phase, key, value, expected in cases:
        result = _resolve_answer_text(phase, key, value, pending_options={})
        ok = result == expected
        print(f"{'✓' if ok else '✗'} P{phase} {key}: '{value}' → '{result}'"
              + ("" if ok else f" (expected '{expected}')"))
        passed += ok
        failed += (not ok)

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_snapshot_precedence():
    """Snapshot label wins over static (covers re-generated AI options)."""
    print("\n" + "=" * 60)
    print("Test: snapshot takes precedence over static definition")
    print("=" * 60)

    # Snapshot overrides the static phase-3 methodology_approach label.
    snapshot = {"methodology_approach": {"A": "Kuantitatif (eksperimen terkontrol)"}}
    result = _resolve_answer_text(
        "3", "methodology_approach", "A", pending_options=snapshot
    )
    expected = "Kuantitatif (eksperimen terkontrol)"
    ok = result == expected
    print(f"{'✓' if ok else '✗'} methodology_approach: 'A' → '{result}'"
          + ("" if ok else f" (expected '{expected}')"))
    return ok


def main():
    r1 = test_snapshot_ai_generated()
    r2 = test_static_still_works_without_snapshot()
    r3 = test_snapshot_precedence()
    print("\n" + "=" * 60)
    if r1 and r2 and r3:
        print("✓ ALL SNAPSHOT TESTS PASSED")
        print("=" * 60)
        return 0
    print("✗ SOME TESTS FAILED")
    print("=" * 60)
    return 1


if __name__ == "__main__":
    sys.exit(main())
