"""Test all fetchers systematically"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from test_framework import test_fetcher_by_name

# List of all fetchers to test
FETCHERS = [
    # Free APIs - no key required
    ("arxiv", "deep learning", "Free API, direct PDF links"),
    ("pubmed", "cancer treatment", "Free API, PMC has free PDFs"),
    ("crossref", "machine learning", "Free API, metadata only"),
    ("openalex", "artificial intelligence", "Free API, good coverage"),
    ("dblp", "computer science", "Free API, CS papers"),
    ("semantic_scholar", "neural networks", "Free API, good metadata"),
    ("europepmc", "medical research", "Free API, biomedical papers"),

    # APIs that may require keys
    ("ieee", "signal processing", "Requires IEEE_API_KEY"),
    ("scopus", "engineering", "Requires SCOPUS_API_KEY"),
    ("springer", "physics", "May require API key"),
    ("sciencedirect", "chemistry", "Requires API key"),
    ("wiley", "biology", "May require credentials"),
    ("taylor_francis", "social science", "May require credentials"),
    ("oxford", "literature", "May require credentials"),
    ("cambridge", "mathematics", "May require credentials"),
    ("emerald", "business", "May require credentials"),
    ("jstor", "history", "Requires credentials"),
    ("proquest", "dissertations", "Requires credentials"),
    ("ebscohost", "academic research", "Requires credentials"),
    ("asce", "civil engineering", "Requires credentials"),
    ("igi_global", "information science", "May require credentials"),
    ("mcgrawhill", "education", "Requires credentials"),
    ("clinicalkey", "clinical medicine", "Requires credentials"),
    ("embase", "pharmacology", "Requires credentials"),
    ("westlaw", "legal research", "Requires credentials"),
    ("sinta", "indonesian research", "Indonesian research database"),
]


def test_all():
    """Test all fetchers and generate master report"""
    print("="*80)
    print("TESTING ALL FETCHERS")
    print("="*80)
    print(f"Total fetchers to test: {len(FETCHERS)}\n")

    results_summary = {
        "test_time": datetime.now().isoformat(),
        "total_fetchers": len(FETCHERS),
        "tested": 0,
        "success": 0,
        "partial_success": 0,
        "failed": 0,
        "no_results": 0,
        "error": 0,
        "fetchers": []
    }

    for i, (fetcher_name, query, note) in enumerate(FETCHERS, 1):
        print(f"\n{'#'*80}")
        print(f"TEST {i}/{len(FETCHERS)}: {fetcher_name}")
        print(f"Note: {note}")
        print(f"{'#'*80}")

        try:
            result = test_fetcher_by_name(fetcher_name, query, limit=3)

            if result:
                results_summary["tested"] += 1
                status = result.get("status", "unknown")

                if status == "success":
                    results_summary["success"] += 1
                elif status == "partial_success":
                    results_summary["partial_success"] += 1
                elif status == "no_results":
                    results_summary["no_results"] += 1
                elif status == "error":
                    results_summary["error"] += 1
                else:
                    results_summary["failed"] += 1

                results_summary["fetchers"].append({
                    "name": fetcher_name,
                    "status": status,
                    "papers_found": result.get("papers_found", 0),
                    "valid_links": result.get("valid_download_links", 0),
                    "note": note
                })
            else:
                results_summary["error"] += 1
                results_summary["fetchers"].append({
                    "name": fetcher_name,
                    "status": "import_error",
                    "papers_found": 0,
                    "valid_links": 0,
                    "note": note
                })

        except KeyboardInterrupt:
            print("\n\n⚠️  Testing interrupted by user")
            break
        except Exception as e:
            print(f"\n✗ Unexpected error: {e}")
            results_summary["error"] += 1
            results_summary["fetchers"].append({
                "name": fetcher_name,
                "status": "exception",
                "papers_found": 0,
                "valid_links": 0,
                "note": note,
                "error": str(e)
            })

        # Small delay between tests to be nice to APIs
        if i < len(FETCHERS):
            import time
            time.sleep(2)

    # Save master report
    report_dir = "/home/sirobo/papergenerator/backend/slr/fetchers/laporan"
    os.makedirs(report_dir, exist_ok=True)

    master_report = os.path.join(report_dir, "master_report.json")
    with open(master_report, "w", encoding="utf-8") as f:
        json.dump(results_summary, f, indent=2, ensure_ascii=False)

    # Create human-readable summary
    summary_file = os.path.join(report_dir, "master_summary.txt")
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write("MASTER TEST REPORT - ALL FETCHERS\n")
        f.write("="*80 + "\n\n")
        f.write(f"Test Time: {results_summary['test_time']}\n")
        f.write(f"Total Fetchers: {results_summary['total_fetchers']}\n")
        f.write(f"Tested: {results_summary['tested']}\n\n")

        f.write("Results Summary:\n")
        f.write(f"  ✓ Success: {results_summary['success']}\n")
        f.write(f"  ⚠ Partial Success: {results_summary['partial_success']}\n")
        f.write(f"  ○ No Results: {results_summary['no_results']}\n")
        f.write(f"  ✗ Failed: {results_summary['failed']}\n")
        f.write(f"  ✗ Error: {results_summary['error']}\n\n")

        f.write("="*80 + "\n")
        f.write("DETAILED RESULTS\n")
        f.write("="*80 + "\n\n")

        for fetcher in results_summary['fetchers']:
            status_icon = {
                "success": "✓",
                "partial_success": "⚠",
                "no_results": "○",
                "error": "✗",
                "import_error": "✗",
                "exception": "✗"
            }.get(fetcher['status'], "?")

            f.write(f"{status_icon} {fetcher['name']:<20} | Status: {fetcher['status']:<15} | ")
            f.write(f"Papers: {fetcher['papers_found']:>2} | Valid Links: {fetcher['valid_links']:>2}\n")
            f.write(f"   Note: {fetcher['note']}\n")
            if 'error' in fetcher:
                f.write(f"   Error: {fetcher['error']}\n")
            f.write("\n")

    print("\n" + "="*80)
    print("MASTER SUMMARY")
    print("="*80)
    print(f"Total Tested: {results_summary['tested']}/{results_summary['total_fetchers']}")
    print(f"✓ Success: {results_summary['success']}")
    print(f"⚠ Partial Success: {results_summary['partial_success']}")
    print(f"○ No Results: {results_summary['no_results']}")
    print(f"✗ Failed/Error: {results_summary['failed'] + results_summary['error']}")
    print(f"\n📄 Master report: {master_report}")
    print(f"📄 Master summary: {summary_file}")
    print("="*80)


if __name__ == "__main__":
    test_all()
