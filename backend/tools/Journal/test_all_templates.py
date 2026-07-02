#!/usr/bin/env python3
"""
Test semua template generator (49 templates).
Output dibagi 2 kelompok: KOMPATIBEL dan TIDAK KOMPATIBEL.
"""

import sys
import json
import traceback
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

# Sample paper data untuk testing
SAMPLE_PAPER = {
    "title": "Deep Learning for Natural Language Processing: A Comprehensive Review",
    "authors": [
        {"name": "John Smith", "affiliation": "University of Technology", "email": "john@univ.edu"},
        {"name": "Jane Doe", "affiliation": "Research Institute", "email": "jane@ri.edu"},
    ],
    "abstract": "This paper presents a comprehensive review of deep learning techniques applied to natural language processing tasks. We analyze transformer architectures, attention mechanisms, and their applications in machine translation, sentiment analysis, and question answering systems. Our findings demonstrate significant improvements in model performance compared to traditional approaches.",
    "keywords": ["deep learning", "natural language processing", "transformers", "attention mechanism", "neural networks"],
    "introduction": "Natural language processing has undergone a revolution with the advent of deep learning. Traditional rule-based systems have been largely replaced by neural network models that learn representations from data automatically.",
    "literature_review": "The field of NLP has seen remarkable progress in recent years. Word embeddings, introduced by Mikolov et al., revolutionized how we represent text. Recurrent neural networks provided a way to process sequential data, while LSTMs addressed the vanishing gradient problem.",
    "methodology": "We conducted experiments using transformer-based models on multiple NLP benchmarks. Our methodology includes data preprocessing, model architecture design, training procedures, and evaluation metrics.",
    "results": "Our experiments show that transformer models achieve state-of-the-art performance on all tested benchmarks. Fine-tuning pre-trained models yields the best results with minimal computational overhead.",
    "discussion": "The success of transformer models can be attributed to their ability to capture long-range dependencies through self-attention. However, these models require significant computational resources for training.",
    "conclusion": "Deep learning has transformed natural language processing, with transformer architectures leading the way. Future research should focus on efficiency improvements and reducing model sizes.",
    "references": [
        {"authors": "Vaswani, A. et al.", "title": "Attention is All You Need", "year": "2017", "venue": "NeurIPS"},
        {"authors": "Devlin, J. et al.", "title": "BERT: Pre-training of Deep Bidirectional Transformers", "year": "2018", "venue": "NAACL"},
        {"authors": "Brown, T. et al.", "title": "Language Models are Few-Shot Learners", "year": "2020", "venue": "NeurIPS"},
        {"authors": "Mikolov, T. et al.", "title": "Distributed Representations of Words", "year": "2013", "venue": "NeurIPS"},
        {"authors": "Hochreiter, S. et al.", "title": "Long Short-Term Memory", "year": "1997", "venue": "Neural Computation"},
    ],
}


@dataclass
class TestResult:
    template: str
    success: bool
    error: str = ""
    output_path: str = ""
    elapsed_sec: float = 0.0


def get_all_generators():
    """Get all *gen.py files in Journal directory."""
    journal_dir = Path(__file__).resolve().parent
    generators = {}
    
    for gen_file in sorted(journal_dir.glob("*gen.py")):
        template_name = gen_file.stem.replace("gen", "").upper()
        generators[template_name] = gen_file
    
    return generators


def test_generator(template_name: str, gen_file: Path, output_dir: Path) -> TestResult:
    """Test a single generator."""
    import time
    start = time.monotonic()
    
    try:
        # Import the generator module
        import importlib.util
        spec = importlib.util.spec_from_file_location(gen_file.stem, gen_file)
        if spec is None or spec.loader is None:
            return TestResult(
                template=template_name,
                success=False,
                error="Could not load module specification",
                elapsed_sec=time.monotonic() - start
            )
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Check if module has build_document function
        if not hasattr(module, "build_document"):
            return TestResult(
                template=template_name,
                success=False,
                error="No build_document() function found",
                elapsed_sec=time.monotonic() - start
            )
        
        # Create temp JSON input
        temp_json = output_dir / f"_temp_{template_name.lower()}.json"
        with open(temp_json, "w", encoding="utf-8") as f:
            json.dump(SAMPLE_PAPER, f, indent=2, ensure_ascii=False)
        
        # Create output path
        output_docx = output_dir / f"test_{template_name.lower()}.docx"
        
        # Try to build document
        try:
            # Most generators have signature: build_document(json_path, output_path, [template_path])
            if hasattr(module, "TEMPLATE_PATH"):
                result = module.build_document(temp_json, output_docx, module.TEMPLATE_PATH)
            else:
                result = module.build_document(temp_json, output_docx)
            
            elapsed = time.monotonic() - start
            
            if output_docx.exists():
                return TestResult(
                    template=template_name,
                    success=True,
                    output_path=str(output_docx),
                    elapsed_sec=elapsed
                )
            else:
                return TestResult(
                    template=template_name,
                    success=False,
                    error="Output file not created",
                    elapsed_sec=elapsed
                )
        
        except TypeError as e:
            # Try alternative signatures
            elapsed = time.monotonic() - start
            return TestResult(
                template=template_name,
                success=False,
                error=f"Signature error: {str(e)[:100]}",
                elapsed_sec=elapsed
            )
    
    except Exception as e:
        elapsed = time.monotonic() - start
        error_msg = f"{type(e).__name__}: {str(e)[:150]}"
        return TestResult(
            template=template_name,
            success=False,
            error=error_msg,
            elapsed_sec=elapsed
        )


def main():
    print("=" * 70)
    print("TEMPLATE GENERATOR CHECKER - ALL TEMPLATES")
    print("=" * 70)
    print(f"Started: {datetime.now().isoformat()}")
    print()
    
    # Setup output directory
    output_dir = Path(__file__).resolve().parent / "output" / "template_test"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Get all generators
    generators = get_all_generators()
    print(f"Found {len(generators)} template generators\n")
    
    # Test each generator
    results: List[TestResult] = []
    
    for i, (template_name, gen_file) in enumerate(generators.items(), 1):
        print(f"[{i:2d}/{len(generators)}] Testing {template_name:15s} ... ", end="", flush=True)
        result = test_generator(template_name, gen_file, output_dir)
        results.append(result)
        
        if result.success:
            print(f"✓ OK ({result.elapsed_sec:.2f}s)")
        else:
            print(f"✗ FAIL ({result.elapsed_sec:.2f}s)")
    
    # Divide into 2 groups
    kelompok_1 = [r for r in results if r.success]  # KOMPATIBEL
    kelompok_2 = [r for r in results if not r.success]  # TIDAK KOMPATIBEL
    
    # Summary
    print()
    print("=" * 70)
    print("HASIL PEMERIKSAAN")
    print("=" * 70)
    
    print()
    print(f"KELOMPOK 1: KOMPATIBEL ({len(kelompok_1)} templates)")
    print("-" * 70)
    for r in kelompok_1:
        print(f"  ✓ {r.template:15s} | {r.elapsed_sec:.2f}s | {Path(r.output_path).name}")
    
    print()
    print(f"KELOMPOK 2: TIDAK KOMPATIBEL ({len(kelompok_2)} templates)")
    print("-" * 70)
    for r in kelompok_2:
        error_short = r.error[:60] + "..." if len(r.error) > 60 else r.error
        print(f"  ✗ {r.template:15s} | {error_short}")
    
    # Save results to JSON
    output_json = output_dir / "test_results.json"
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "date": datetime.now().isoformat(),
                "total_templates": len(results),
                "kelompok_1_kompatibel": len(kelompok_1),
                "kelompok_2_tidak_kompatibel": len(kelompok_2),
            },
            "kelompok_1_kompatibel": [
                {"template": r.template, "output": r.output_path, "elapsed_sec": r.elapsed_sec}
                for r in kelompok_1
            ],
            "kelompok_2_tidak_kompatibel": [
                {"template": r.template, "error": r.error, "elapsed_sec": r.elapsed_sec}
                for r in kelompok_2
            ],
        }, f, indent=2, ensure_ascii=False)
    
    print()
    print(f"Results saved to: {output_json}")
    print(f"Finished: {datetime.now().isoformat()}")
    print()
    print(f"Total: {len(results)} | Kompitabel: {len(kelompok_1)} | Tidak Kompatibel: {len(kelompok_2)}")


if __name__ == "__main__":
    main()
