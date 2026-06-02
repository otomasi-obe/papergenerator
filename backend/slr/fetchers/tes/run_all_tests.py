#!/usr/bin/env python3
"""
Master test runner - menjalankan semua test fetcher secara berurutan
dan memberikan summary hasil
"""

import subprocess
import sys
from pathlib import Path

# Daftar semua test files
TEST_FILES = [
    "test_arxiv_verified.py",
    "test_crossref_verified.py",
    "test_dblp_verified.py",
    "test_europepmc_verified.py",
    "test_openalex_verified.py",
    "test_pubmed_verified.py",
    "test_semantic_scholar_verified.py",
    "test_ieee_verified.py",
    "test_scopus_verified.py",
    "test_sciencedirect_verified.py",
    "test_springer_verified.py",
    "test_sinta_verified.py",
    "test_taylor_francis_verified.py",
]

def run_test(test_file: str) -> tuple[bool, str]:
    """Run a single test file and return (success, output)"""
    test_path = Path(__file__).parent / test_file
    
    try:
        result = subprocess.run(
            [sys.executable, str(test_path)],
            capture_output=True,
            text=True,
            timeout=120  # 2 minutes timeout per test
        )
        
        output = result.stdout + result.stderr
        success = result.returncode == 0
        
        return success, output
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT: Test exceeded 2 minutes"
    except Exception as e:
        return False, f"ERROR: {str(e)}"

def main():
    print("=" * 100)
    print("MASTER TEST RUNNER - VERIFIKASI SEMUA FETCHERS")
    print("=" * 100)
    print()
    
    results = {}
    
    for i, test_file in enumerate(TEST_FILES, 1):
        fetcher_name = test_file.replace("test_", "").replace("_verified.py", "").upper()
        
        print(f"\n[{i}/{len(TEST_FILES)}] Testing {fetcher_name}...")
        print("-" * 100)
        
        success, output = run_test(test_file)
        results[fetcher_name] = success
        
        # Print output
        print(output)
        
        if success:
            print(f"✅ {fetcher_name}: PASSED")
        else:
            print(f"❌ {fetcher_name}: FAILED")
        
        print("-" * 100)
    
    # Summary
    print("\n" + "=" * 100)
    print("SUMMARY HASIL TEST")
    print("=" * 100)
    
    passed = sum(1 for v in results.values() if v)
    failed = len(results) - passed
    
    print(f"\nTotal Tests: {len(results)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print()
    
    # Detail per fetcher
    print("Detail per Fetcher:")
    for fetcher, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status} - {fetcher}")
    
    print("\n" + "=" * 100)
    
    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
