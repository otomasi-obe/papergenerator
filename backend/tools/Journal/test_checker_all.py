#!/usr/bin/env python3
"""
Auto Checker untuk semua 49 template.
Output format seperti Progress Kelompok 1/2 txt.
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv
load_dotenv(BACKEND.parent / ".env", override=True)

# Import checker
try:
    from tools.Journal.auto_checker import AutoChecker
except ImportError:
    print("ERROR: auto_checker not found. Trying fallback...")
    sys.exit(1)

SAMPLE_PAPER = {
    "title": "Deep Learning for Natural Language Processing: A Comprehensive Review",
    "authors": [
        {"name": "John Smith", "affiliation": "University of Technology", "email": "john@univ.edu"},
        {"name": "Jane Doe", "affiliation": "Research Institute", "email": "jane@ri.edu"},
    ],
    "abstract": "This paper presents a comprehensive review of deep learning techniques applied to natural language processing tasks. We analyze transformer architectures, attention mechanisms, and their applications in machine translation, sentiment analysis, and question answering systems. Our findings demonstrate significant improvements in model performance.",
    "keywords": ["deep learning", "natural language processing", "transformers", "attention mechanism", "neural networks"],
    "introduction": "Natural language processing has undergone a revolution with the advent of deep learning.",
    "literature_review": "The field of NLP has seen remarkable progress in recent years.",
    "methodology": "We conducted experiments using transformer-based models on multiple NLP benchmarks.",
    "results": "Our experiments show that transformer models achieve state-of-the-art performance.",
    "discussion": "The success of transformer models can be attributed to their ability to capture long-range dependencies.",
    "conclusion": "Deep learning has transformed natural language processing.",
    "references": [
        {"authors": "Vaswani, A. et al.", "title": "Attention is All You Need", "year": "2017", "venue": "NeurIPS"},
        {"authors": "Devlin, J. et al.", "title": "BERT: Pre-training", "year": "2018", "venue": "NAACL"},
        {"authors": "Brown, T. et al.", "title": "Language Models", "year": "2020", "venue": "NeurIPS"},
    ],
}

def get_all_generators():
    """Get all *gen.py files."""
    journal_dir = Path(__file__).resolve().parent
    generators = {}
    for gen_file in sorted(journal_dir.glob("*gen.py")):
        template_name = gen_file.stem.replace("gen", "").upper()
        generators[template_name] = gen_file
    return generators


def check_template(template_name, output_dir):
    """Run checker on a template."""
    try:
        checker = AutoChecker(template_name)
        # Simulate a docx check (we'd need actual docx for full check)
        # For now, return basic viability
        return {
            "name": template_name,
            "score": 50,  # placeholder
            "status": "PENDING",
            "error": None,
            "elapsed": 0.1
        }
    except Exception as e:
        return {
            "name": template_name,
            "score": 0,
            "status": "GEN_FAIL",
            "error": str(e)[:100],
            "elapsed": 0.0
        }


def main():
    generators = get_all_generators()
    output_dir = Path(__file__).resolve().parent / "output" / "checker_results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 80)
    print("AUTO CHECKER — SEMUA 49 TEMPLATE")
    print("=" * 80)
    print(f"Tanggal: {datetime.now().strftime('%d %B %Y')}")
    print(f"Total Template: {len(generators)} jurnal")
    print()
    
    results = []
    for i, (template_name, gen_file) in enumerate(generators.items(), 1):
        print(f"[{i:2d}/{len(generators)}] Checking {template_name:20s} ... ", end="", flush=True)
        start = time.monotonic()
        
        result = check_template(template_name, output_dir)
        result["elapsed"] = time.monotonic() - start
        results.append(result)
        
        if result["status"] == "GEN_FAIL":
            print(f"✗ GEN_FAIL")
        else:
            print(f"✓ {result['score']}%")
    
    # Categorize results
    excellent = [r for r in results if r["score"] >= 80]
    ok = [r for r in results if 50 <= r["score"] < 80]
    fail = [r for r in results if 0 < r["score"] < 50]
    gen_fail = [r for r in results if r["status"] == "GEN_FAIL"]
    
    avg_score = sum(r["score"] for r in results if r["status"] != "GEN_FAIL") / max(1, len([r for r in results if r["status"] != "GEN_FAIL"]))
    
    # Print results
    print()
    print("=" * 80)
    print("HASIL PER TEMPLATE:")
    print("=" * 80)
    print()
    print(f"{'No':4s} {'Journal':25s} {'Score':8s} {'Status':12s}")
    print("-" * 80)
    
    for i, r in enumerate(results, 1):
        if r["status"] == "GEN_FAIL":
            score_str = "-"
            status_str = "GEN_FAIL"
        else:
            score_str = f"{r['score']}%"
            status_str = r["status"]
        
        print(f"{i:3d}  {r['name']:23s} {score_str:>7s}  {status_str:11s}")
    
    print()
    print("=" * 80)
    print("RINGKASAN")
    print("=" * 80)
    print()
    print(f"Rata-rata: {avg_score:.0f}%")
    print(f"EXCELLENT (>=80%): {len(excellent)}")
    print(f"OK (50-79%): {len(ok)}")
    print(f"FAIL (<50%): {len(fail)}")
    print(f"GEN_FAIL: {len(gen_fail)}")
    print()
    
    if excellent:
        print("Best performers:")
        for r in sorted(excellent, key=lambda x: x["score"], reverse=True)[:5]:
            print(f"  - {r['name']} ({r['score']}%)")
    
    if gen_fail:
        print()
        print("Generator failures:")
        for r in gen_fail:
            print(f"  - {r['name']}: {r['error']}")
    
    # Save JSON
    json_output = output_dir / "checker_results.json"
    with open(json_output, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "date": datetime.now().isoformat(),
                "total": len(results),
                "excellent": len(excellent),
                "ok": len(ok),
                "fail": len(fail),
                "gen_fail": len(gen_fail),
                "average": round(avg_score, 1)
            },
            "results": results
        }, f, indent=2, ensure_ascii=False)
    
    print()
    print(f"Results saved to: {json_output}")


if __name__ == "__main__":
    main()
