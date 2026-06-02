"""Test Group 1: arxiv, asce, cambridge - with timeout handling"""
import sys
from pathlib import Path
import signal
import json

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from test_framework import FetcherTester


class TimeoutException(Exception):
    pass


def timeout_handler(signum, frame):
    raise TimeoutException("Operation timed out")


def test_fetcher_with_timeout(fetcher_name, fetcher_module, query, timeout_seconds=45):
    """Test a fetcher with a timeout"""
    print(f"\n{'='*80}")
    print(f"GROUP 1 - Testing: {fetcher_name}")
    print(f"{'='*80}")
    
    try:
        # Set up timeout
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout_seconds)
        
        tester = FetcherTester(fetcher_name, query)
        result = tester.test_fetcher(fetcher_module, limit=5)
        
        # Cancel timeout
        signal.alarm(0)
        
        return result
    except TimeoutException:
        signal.alarm(0)
        print(f"\n❌ {fetcher_name} timed out after {timeout_seconds} seconds")
        return {
            "fetcher": fetcher_name,
            "status": "timeout",
            "errors": [f"Timed out after {timeout_seconds} seconds - possible network issue"]
        }
    except Exception as e:
        signal.alarm(0)
        print(f"\n❌ Error testing {fetcher_name}: {e}")
        return {
            "fetcher": fetcher_name,
            "status": "error",
            "errors": [str(e)]
        }


def test_group_1():
    results = []
    
    # Test arxiv - preprint server
    print("\n" + "="*80)
    print("GROUP 1 - TEST 1/3: arXiv")
    print("="*80)
    try:
        from slr.fetchers import arxiv
        result = test_fetcher_with_timeout("arxiv", arxiv, "quantum computing", timeout_seconds=45)
        results.append(result)
    except Exception as e:
        print(f"Error loading arxiv: {e}")
        results.append({"fetcher": "arxiv", "status": "error", "errors": [str(e)]})
    
    # Test asce - civil engineering
    print("\n" + "="*80)
    print("GROUP 1 - TEST 2/3: ASCE")
    print("="*80)
    try:
        from slr.fetchers import asce
        result = test_fetcher_with_timeout("asce", asce, "structural engineering", timeout_seconds=45)
        results.append(result)
    except Exception as e:
        print(f"Error loading asce: {e}")
        results.append({"fetcher": "asce", "status": "error", "errors": [str(e)]})
    
    # Test cambridge
    print("\n" + "="*80)
    print("GROUP 1 - TEST 3/3: Cambridge")
    print("="*80)
    try:
        from slr.fetchers import cambridge
        result = test_fetcher_with_timeout("cambridge", cambridge, "mathematics education", timeout_seconds=45)
        results.append(result)
    except Exception as e:
        print(f"Error loading cambridge: {e}")
        results.append({"fetcher": "cambridge", "status": "error", "errors": [str(e)]})
    
    # Save results
    output_file = Path(__file__).parent.parent / "hasil" / "group_1_results.json"
    output_file.parent.mkdir(exist_ok=True)
    
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    print("\n" + "="*80)
    print("GROUP 1 TEST SUMMARY")
    print("="*80)
    for result in results:
        fetcher = result.get("fetcher", "unknown")
        status = result.get("status", "unknown")
        papers = result.get("papers_found", 0)
        print(f"\n{fetcher}:")
        print(f"  Status: {status}")
        if status in ("success", "completed"):
            print(f"  Papers found: {papers}")
            print(f"  Papers with URLs: {result.get('papers_with_urls', 0)}")
            print(f"  Valid download links: {result.get('valid_download_links', 0)}")
        elif "errors" in result:
            print(f"  Errors: {result['errors']}")
    
    print(f"\n✓ Group 1 results saved to {output_file}")
    return results


if __name__ == "__main__":
    test_group_1()
