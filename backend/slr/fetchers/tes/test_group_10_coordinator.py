"""Master Coordinator - Compile all test results and generate final report"""
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

def compile_results():
    """Compile all group results into master report"""
    hasil_dir = Path(__file__).parent.parent / "hasil"
    
    master_report = {
        "test_run": datetime.now().isoformat(),
        "total_fetchers": 26,
        "groups_tested": 9,
        "summary": {
            "success": 0,
            "partial_success": 0,
            "no_results": 0,
            "error": 0,
            "total_papers_found": 0,
            "total_valid_links": 0
        },
        "fetchers": [],
        "group_results": []
    }
    
    # Collect results from all groups
    for i in range(1, 10):
        group_file = hasil_dir / f"group_{i}_results.json"
        if group_file.exists():
            with open(group_file, "r") as f:
                group_data = json.load(f)
                master_report["group_results"].append({
                    "group": i,
                    "file": str(group_file),
                    "fetchers_count": len(group_data)
                })
                
                # Process each fetcher result
                for fetcher_result in group_data:
                    status = fetcher_result.get("status", "unknown")
                    
                    if status == "success":
                        master_report["summary"]["success"] += 1
                    elif status == "partial_success":
                        master_report["summary"]["partial_success"] += 1
                    elif status == "no_results":
                        master_report["summary"]["no_results"] += 1
                    else:
                        master_report["summary"]["error"] += 1
                    
                    master_report["summary"]["total_papers_found"] += fetcher_result.get("papers_found", 0)
                    master_report["summary"]["total_valid_links"] += fetcher_result.get("valid_download_links", 0)
                    
                    master_report["fetchers"].append({
                        "name": fetcher_result.get("fetcher", "unknown"),
                        "status": status,
                        "papers_found": fetcher_result.get("papers_found", 0),
                        "valid_links": fetcher_result.get("valid_download_links", 0),
                        "group": i
                    })
        else:
            print(f"⚠️  Group {i} results not found: {group_file}")
    
    # Save master report
    master_file = hasil_dir / "MASTER_REPORT.json"
    with open(master_file, "w") as f:
        json.dump(master_report, f, indent=2)
    
    # Generate human-readable summary
    summary_file = hasil_dir / "SUMMARY.txt"
    with open(summary_file, "w") as f:
        f.write("="*80 + "\n")
        f.write("FETCHER TEST RESULTS - MASTER SUMMARY\n")
        f.write("="*80 + "\n\n")
        f.write(f"Test Run: {master_report['test_run']}\n")
        f.write(f"Total Fetchers: {master_report['total_fetchers']}\n")
        f.write(f"Groups Tested: {master_report['groups_tested']}\n\n")
        
        f.write("OVERALL SUMMARY:\n")
        f.write("-"*80 + "\n")
        f.write(f"✓ Success: {master_report['summary']['success']}\n")
        f.write(f"⚠ Partial Success: {master_report['summary']['partial_success']}\n")
        f.write(f"○ No Results: {master_report['summary']['no_results']}\n")
        f.write(f"✗ Error: {master_report['summary']['error']}\n")
        f.write(f"\nTotal Papers Found: {master_report['summary']['total_papers_found']}\n")
        f.write(f"Total Valid PDF Links: {master_report['summary']['total_valid_links']}\n\n")
        
        f.write("FETCHER DETAILS:\n")
        f.write("-"*80 + "\n")
        
        for fetcher in sorted(master_report["fetchers"], key=lambda x: x["name"]):
            status_icon = {
                "success": "✓",
                "partial_success": "⚠",
                "no_results": "○",
                "error": "✗"
            }.get(fetcher["status"], "?")
            
            f.write(f"{status_icon} {fetcher['name']:20s} | ")
            f.write(f"Papers: {fetcher['papers_found']:3d} | ")
            f.write(f"Valid Links: {fetcher['valid_links']:3d} | ")
            f.write(f"Group: {fetcher['group']}\n")
    
    print("\n" + "="*80)
    print("MASTER REPORT GENERATED")
    print("="*80)
    print(f"Master Report: {master_file}")
    print(f"Summary: {summary_file}")
    print("\nOVERALL SUMMARY:")
    print(f"  ✓ Success: {master_report['summary']['success']}")
    print(f"  ⚠ Partial: {master_report['summary']['partial_success']}")
    print(f"  ○ No Results: {master_report['summary']['no_results']}")
    print(f"  ✗ Error: {master_report['summary']['error']}")
    print(f"\n  Total Papers: {master_report['summary']['total_papers_found']}")
    print(f"  Valid Links: {master_report['summary']['total_valid_links']}")
    print("="*80 + "\n")
    
    return master_report

if __name__ == "__main__":
    compile_results()
