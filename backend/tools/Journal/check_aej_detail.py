#!/usr/bin/env python3
"""
Checker untuk template AEJ - Generate sample dokumen dan audit dengan auto_checker.
"""

import sys
import json
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv
load_dotenv(BACKEND.parent / ".env", override=True)

# Sample paper data
SAMPLE_PAPER = {
    "title": "Deep Learning for Natural Language Processing: A Comprehensive Review",
    "authors": [
        {"name": "John Smith", "affiliation": "University of Technology", "email": "john@univ.edu"},
        {"name": "Jane Doe", "affiliation": "Research Institute", "email": "jane@ri.edu"},
    ],
    "abstract": "This paper presents a comprehensive review of deep learning techniques applied to natural language processing tasks. We analyze transformer architectures, attention mechanisms, and their applications in machine translation, sentiment analysis, and question answering systems.",
    "keywords": ["deep learning", "natural language processing", "transformers", "attention mechanism", "neural networks"],
    "introduction": "Natural language processing has undergone a revolution with the advent of deep learning.",
    "literature_review": "The field of NLP has seen remarkable progress. Word embeddings revolutionized text representation.",
    "methodology": "We conducted experiments using transformer-based models on multiple NLP benchmarks.",
    "results": "Our experiments show state-of-the-art performance on all tested benchmarks.",
    "discussion": "The success of transformer models can be attributed to their ability to capture long-range dependencies.",
    "conclusion": "Deep learning has transformed natural language processing.",
    "references": [
        {"authors": "Vaswani, A. et al.", "title": "Attention is All You Need", "year": "2017", "venue": "NeurIPS"},
        {"authors": "Devlin, J. et al.", "title": "BERT: Pre-training", "year": "2018", "venue": "NAACL"},
        {"authors": "Brown, T. et al.", "title": "Language Models", "year": "2020", "venue": "NeurIPS"},
    ],
}

def main():
    journal_dir = Path(__file__).resolve().parent
    
    print("=" * 80)
    print("CHECKER DETAIL - TEMPLATE AEJ")
    print("=" * 80)
    print()
    
    # Check 1: Module load
    print("[1/3] Checking module load...")
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("AEJgen", journal_dir / "AEJgen.py")
        if spec is None or spec.loader is None:
            print("  ✗ FAIL: Could not load module spec")
            return
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print("  ✓ OK: Module loaded successfully")
    except Exception as e:
        print(f"  ✗ FAIL: {type(e).__name__}: {e}")
        return
    
    # Check 2: build_document function
    print()
    print("[2/3] Checking build_document() function...")
    if hasattr(module, "build_document"):
        print("  ✓ OK: build_document() found")
    else:
        print("  ✗ FAIL: build_document() not found")
        print()
        print("  Available functions:")
        funcs = [name for name in dir(module) if callable(getattr(module, name)) and not name.startswith("_")]
        for f in funcs[:10]:
            print(f"    - {f}()")
        if len(funcs) > 10:
            print(f"    ... and {len(funcs) - 10} more")
        return
    
    # Check 3: Try to generate
    print()
    print("[3/3] Trying to generate sample document...")
    try:
        # Create temp JSON
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(SAMPLE_PAPER, f, ensure_ascii=False)
            temp_json = f.name
        
        temp_output = Path(tempfile.mktemp(suffix=".docx"))
        
        # Try to call build_document
        result = module.build_document(temp_json, temp_output)
        
        if temp_output.exists():
            file_size = temp_output.stat().st_size
            print(f"  ✓ OK: Generated {temp_output.name} ({file_size} bytes)")
        else:
            print(f"  ✗ FAIL: Output file not created")
    
    except Exception as e:
        print(f"  ✗ FAIL: {type(e).__name__}")
        print(f"    {str(e)[:200]}")
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    main()
