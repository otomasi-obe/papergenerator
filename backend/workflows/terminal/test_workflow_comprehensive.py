#!/usr/bin/env python3
"""
Comprehensive workflow test - simulates answering questions and verifies full text storage.
"""

import sys
import json
from pathlib import Path

# Add backend to path
BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

# Mock database for testing
class MockProjectMemory:
    _storage = {}
    
    @classmethod
    def query(cls):
        return cls
    
    @classmethod
    def filter_by(cls, **kwargs):
        key = f"{kwargs.get('paper_id')}_{kwargs.get('user_id')}_{kwargs.get('key')}"
        return cls._MockQuery(key)
    
    class _MockQuery:
        def __init__(self, key):
            self.key = key
        
        def first(self):
            if self.key in MockProjectMemory._storage:
                return MockProjectMemory._storage[self.key]
            return None
    
    def __init__(self, paper_id, user_id, key, value, kind):
        self.paper_id = paper_id
        self.user_id = user_id
        self.key = key
        self.value = value
        self.kind = kind
        storage_key = f"{paper_id}_{user_id}_{key}"
        MockProjectMemory._storage[storage_key] = self

class MockDB:
    class session:
        @staticmethod
        def add(obj):
            pass
        
        @staticmethod
        def commit():
            pass

# Patch the imports
import workflows.tool as tool_module
tool_module.ProjectMemory = MockProjectMemory
tool_module.db = MockDB

from workflows.tool import save_workflow_answers, _get_workflow_state

def test_workflow_full_text_storage():
    """Test that workflow stores full text instead of letter codes."""
    print("=" * 70)
    print("COMPREHENSIVE WORKFLOW TEST - Full Text Storage")
    print("=" * 70)
    
    paper_id = "test_paper_001"
    user_id = "test_user_001"
    
    # Phase 0 - Pre-Questionnaire
    print("\n[Phase 0] Pre-Questionnaire - Status Awal")
    print("-" * 70)
    
    phase_0_answers = [
        {"key": "progress_level", "value": "A"},  # Should become "Masih ide/konsep"
        {"key": "data_readiness", "value": "D"},  # Should become "Hasil final sudah siap"
        {"key": "team_size", "value": "A"},       # Should become "Individu (tugas akhir)"
    ]
    
    result = save_workflow_answers(paper_id, user_id, "0", phase_0_answers)
    print(f"Result: {result['kind']}")
    print(f"Next phase: {result.get('next_phase', 'N/A')}")
    
    # Verify stored values
    state = _get_workflow_state(paper_id, user_id)
    answers = state.get("answers", {})
    
    print("\nStored answers:")
    for key, value in answers.items():
        print(f"  {key}: '{value}'")
    
    # Verify full text is stored
    assert answers["progress_level"] == "Masih ide/konsep", \
        f"Expected 'Masih ide/konsep', got '{answers['progress_level']}'"
    assert answers["data_readiness"] == "Hasil final sudah siap", \
        f"Expected 'Hasil final sudah siap', got '{answers['data_readiness']}'"
    assert answers["team_size"] == "Individu (tugas akhir)", \
        f"Expected 'Individu (tugas akhir)', got '{answers['team_size']}'"
    
    print("✓ Phase 0 answers stored as full text")
    
    # Phase 1 - Profil Dasar Paper
    print("\n[Phase 1] Profil Dasar Paper")
    print("-" * 70)
    
    phase_1_answers = [
        {"key": "field", "value": "A"},              # Should become "Ilmu Komputer & IT"
        {"key": "paper_type", "value": "B"},         # Should become "Research Paper"
        {"key": "target_publication", "value": "A"}, # Should become "Tugas Akhir / Skripsi / Tesis"
        {"key": "title", "value": "Implementasi Machine Learning untuk Prediksi Cuaca"},  # Custom text
    ]
    
    result = save_workflow_answers(paper_id, user_id, "1", phase_1_answers)
    print(f"Result: {result['kind']}")
    print(f"Next phase: {result.get('next_phase', 'N/A')}")
    
    # Verify stored values
    state = _get_workflow_state(paper_id, user_id)
    answers = state.get("answers", {})
    
    print("\nStored answers (cumulative):")
    for key, value in answers.items():
        print(f"  {key}: '{value}'")
    
    # Verify full text is stored
    assert answers["field"] == "Ilmu Komputer & IT", \
        f"Expected 'Ilmu Komputer & IT', got '{answers['field']}'"
    assert answers["paper_type"] == "Research Paper", \
        f"Expected 'Research Paper', got '{answers['paper_type']}'"
    assert answers["target_publication"] == "Tugas Akhir / Skripsi / Tesis", \
        f"Expected 'Tugas Akhir / Skripsi / Tesis', got '{answers['target_publication']}'"
    assert answers["title"] == "Implementasi Machine Learning untuk Prediksi Cuaca", \
        f"Custom title not stored correctly"
    
    print("✓ Phase 1 answers stored as full text")
    
    # Phase 3 - Metodologi & Data
    print("\n[Phase 3] Metodologi & Data")
    print("-" * 70)
    
    phase_3_answers = [
        {"key": "methodology_approach", "value": "A"},  # Should become "Kuantitatif"
        {"key": "specific_method", "value": "Random Forest Classification"},  # Custom text
        {"key": "data_source", "value": "Dataset cuaca historis dari BMKG"},  # Custom text
        {"key": "ethics", "value": "A"},  # Should become "Tidak perlu etik"
    ]
    
    result = save_workflow_answers(paper_id, user_id, "3", phase_3_answers)
    print(f"Result: {result['kind']}")
    print(f"Next phase: {result.get('next_phase', 'N/A')}")
    
    # Verify stored values
    state = _get_workflow_state(paper_id, user_id)
    answers = state.get("answers", {})
    
    print("\nStored answers (cumulative):")
    for key, value in answers.items():
        print(f"  {key}: '{value}'")
    
    # Verify full text is stored
    assert answers["methodology_approach"] == "Kuantitatif", \
        f"Expected 'Kuantitatif', got '{answers['methodology_approach']}'"
    assert answers["specific_method"] == "Random Forest Classification", \
        f"Custom method not stored correctly"
    assert answers["ethics"] == "Tidak perlu etik", \
        f"Expected 'Tidak perlu etik', got '{answers['ethics']}'"
    
    print("✓ Phase 3 answers stored as full text")
    
    # Phase 5 - Literatur & Sitasi
    print("\n[Phase 5] Literatur & Sitasi")
    print("-" * 70)
    
    phase_5_answers = [
        {"key": "citation_style", "value": "B"},      # Should become "IEEE (Teknik, CS)"
        {"key": "reference_count", "value": "C"},     # Should become "40-60"
        {"key": "reference_years", "value": "A"},     # Should become "5 tahun terakhir"
        {"key": "reference_tool", "value": "A"},      # Should become "Mendeley"
    ]
    
    result = save_workflow_answers(paper_id, user_id, "5", phase_5_answers)
    print(f"Result: {result['kind']}")
    print(f"Next phase: {result.get('next_phase', 'N/A')}")
    
    # Verify stored values
    state = _get_workflow_state(paper_id, user_id)
    answers = state.get("answers", {})
    
    print("\nFinal stored answers:")
    for key, value in answers.items():
        print(f"  {key}: '{value}'")
    
    # Verify full text is stored
    assert answers["citation_style"] == "IEEE (Teknik, CS)", \
        f"Expected 'IEEE (Teknik, CS)', got '{answers['citation_style']}'"
    assert answers["reference_count"] == "40-60", \
        f"Expected '40-60', got '{answers['reference_count']}'"
    assert answers["reference_years"] == "5 tahun terakhir", \
        f"Expected '5 tahun terakhir', got '{answers['reference_years']}'"
    assert answers["reference_tool"] == "Mendeley", \
        f"Expected 'Mendeley', got '{answers['reference_tool']}'"
    
    print("✓ Phase 5 answers stored as full text")
    
    # Final verification
    print("\n" + "=" * 70)
    print("FINAL VERIFICATION")
    print("=" * 70)
    
    print("\nAll answers stored in workflow_state:")
    print(json.dumps(answers, indent=2, ensure_ascii=False))
    
    # Check that NO letter codes are stored (except for custom answers that might contain letters)
    letter_codes = ["A", "B", "C", "D"]
    problematic_keys = []
    for key, value in answers.items():
        if value in letter_codes:
            problematic_keys.append(key)
    
    if problematic_keys:
        print(f"\n✗ WARNING: Found letter codes in: {problematic_keys}")
        return False
    else:
        print("\n✓ SUCCESS: All answers stored as full text, no letter codes found")
        return True

def main():
    """Run the comprehensive test."""
    try:
        success = test_workflow_full_text_storage()
        
        print("\n" + "=" * 70)
        if success:
            print("✓ ALL TESTS PASSED - Workflow stores full text correctly")
        else:
            print("✗ TESTS FAILED - Some answers still stored as letter codes")
        print("=" * 70 + "\n")
        
        return 0 if success else 1
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
