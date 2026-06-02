#!/usr/bin/env python3
"""
Test script to verify workflow stores full text instead of letter codes.
"""

import sys
from pathlib import Path

# Add backend to path
BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

# Import workflow functions
from workflows.tool import _resolve_answer_text
from workflows.engine import WORKFLOW_PHASES

def test_resolve_answer_text():
    """Test the _resolve_answer_text function."""
    print("=" * 60)
    print("Testing _resolve_answer_text function")
    print("=" * 60)
    
    # Test Phase 0 questions
    test_cases = [
        ("0", "progress_level", "A", "Masih ide/konsep"),
        ("0", "progress_level", "B", "Sudah ada judul & outline"),
        ("0", "data_readiness", "D", "Hasil final sudah siap"),
        ("0", "team_size", "A", "Individu (tugas akhir)"),
        
        # Test Phase 1 questions
        ("1", "field", "A", "Ilmu Komputer & IT"),
        ("1", "paper_type", "B", "Research Paper"),
        ("1", "target_publication", "A", "Tugas Akhir / Skripsi / Tesis"),
        
        # Test Phase 3 questions
        ("3", "methodology_approach", "A", "Kuantitatif"),
        ("3", "methodology_approach", "B", "Kualitatif"),
        ("3", "ethics", "C", "Butuh informed consent"),
        
        # Test Phase 5 questions
        ("5", "citation_style", "B", "IEEE (Teknik, CS)"),
        ("5", "reference_count", "C", "40-60"),
        ("5", "reference_years", "A", "5 tahun terakhir"),
        
        # Test custom answer (not in options)
        ("1", "title", "My Custom Title", "My Custom Title"),
        ("2", "topic", "Custom Topic Text", "Custom Topic Text"),
    ]
    
    passed = 0
    failed = 0
    
    for phase, key, value, expected in test_cases:
        result = _resolve_answer_text(phase, key, value)
        status = "✓" if result == expected else "✗"
        
        if result == expected:
            passed += 1
            print(f"{status} Phase {phase}, {key}: '{value}' → '{result}'")
        else:
            failed += 1
            print(f"{status} Phase {phase}, {key}: '{value}' → '{result}' (expected: '{expected}')")
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0

def test_phase_6_branches():
    """Test Phase 6 branch conditions with full text."""
    print("\n" + "=" * 60)
    print("Testing Phase 6 branch conditions")
    print("=" * 60)
    
    phase_6 = WORKFLOW_PHASES.get("6", {})
    branches = phase_6.get("branches", {})
    
    # Test quantitative branch
    quant_condition = branches["quantitative"]["condition"]
    
    test_answers = [
        ({"methodology_approach": "A"}, True, "Letter code A"),
        ({"methodology_approach": "Kuantitatif"}, True, "Full text Kuantitatif"),
        ({"methodology_approach": "C"}, True, "Letter code C"),
        ({"methodology_approach": "Mixed-Method"}, True, "Full text Mixed-Method"),
        ({"methodology_approach": "B"}, False, "Letter code B (qualitative)"),
        ({"methodology_approach": "Kualitatif"}, False, "Full text Kualitatif"),
    ]
    
    passed = 0
    failed = 0
    
    for answers, expected, description in test_answers:
        result = quant_condition(answers)
        status = "✓" if result == expected else "✗"
        
        if result == expected:
            passed += 1
            print(f"{status} {description}: {result} (expected: {expected})")
        else:
            failed += 1
            print(f"{status} {description}: {result} (expected: {expected}) - FAILED")
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0

def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("WORKFLOW FULL TEXT STORAGE TEST")
    print("=" * 60 + "\n")
    
    test1_passed = test_resolve_answer_text()
    test2_passed = test_phase_6_branches()
    
    print("\n" + "=" * 60)
    if test1_passed and test2_passed:
        print("✓ ALL TESTS PASSED")
    else:
        print("✗ SOME TESTS FAILED")
    print("=" * 60 + "\n")
    
    return 0 if (test1_passed and test2_passed) else 1

if __name__ == "__main__":
    sys.exit(main())
