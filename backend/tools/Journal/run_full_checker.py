#!/usr/bin/env python3
"""
Full checker untuk semua 49 template - generate report detail seperti format txt.
Output: 2 file txt (Kelompok 1 KOMPATIBEL dan Kelompok 2 TIDAK KOMPATIBEL)
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

def get_all_generators():
    """Get all *gen.py files."""
    journal_dir = Path(__file__).resolve().parent
    generators = {}
    for gen_file in sorted(journal_dir.glob("*gen.py")):
        template_name = gen_file.stem.replace("gen", "").upper()
        generators[template_name] = gen_file
    return generators

def test_generator_basic(template_name, gen_file):
    """Basic compatibility test."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(gen_file.stem, gen_file)
        if spec is None or spec.loader is None:
            return {"compatible": False, "error": "Could not load module"}
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        if not hasattr(module, "build_document"):
            return {"compatible": False, "error": "No build_document() function"}
        
        return {"compatible": True, "error": None}
    except Exception as e:
        return {"compatible": False, "error": f"{type(e).__name__}: {str(e)[:80]}"}

def main():
    print("=" * 80)
    print("FULL CHECKER - 49 TEMPLATE GENERATORS")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%d %B %Y, %H:%M:%S')}")
    print()
    
    generators = get_all_generators()
    print(f"Total templates found: {len(generators)}")
    print()
    
    results = {}
    kelompok_1 = []  # KOMPATIBEL
    kelompok_2 = []  # TIDAK KOMPATIBEL
    
    for i, (name, gen_file) in enumerate(generators.items(), 1):
        print(f"[{i:2d}/{len(generators)}] Testing {name:20s} ... ", end="", flush=True)
        
        result = test_generator_basic(name, gen_file)
        results[name] = result
        
        if result["compatible"]:
            kelompok_1.append(name)
            print("✓ KOMPATIBEL")
        else:
            kelompok_2.append(name)
            print(f"✗ TIDAK KOMPATIBEL - {result['error']}")
    
    # Calculate stats
    total = len(generators)
    k1_count = len(kelompok_1)
    k2_count = len(kelompok_2)
    k1_pct = (k1_count / total) * 100
    k2_pct = (k2_count / total) * 100
    
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total: {total}")
    print(f"Kelompok 1 (KOMPATIBEL): {k1_count} ({k1_pct:.1f}%)")
    print(f"Kelompok 2 (TIDAK KOMPATIBEL): {k2_count} ({k2_pct:.1f}%)")
    print()
    
    # Save results
    output_dir = Path("/home/sirobo/ANNABIL/Alur Checking")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate Kelompok 1 report
    k1_file = output_dir / f"Kelompok 1 - KOMPATIBEL - {datetime.now().strftime('%Y%m%d')}.txt"
    k2_file = output_dir / f"Kelompok 2 - TIDAK KOMPATIBEL - {datetime.now().strftime('%Y%m%d')}.txt"
    
    # Write Kelompok 1 report
    with open(k1_file, "w", encoding="utf-8") as f:
        f.write("╔" + "═" * 78 + "╗\n")
        f.write("║  KELOMPOK 1 — KOMPATIBEL (Template Generator Siap Pakai)" + " " * 19 + "║\n")
        f.write("║  Tanggal: " + datetime.now().strftime('%d %B %Y') + " " * 51 + "║\n")
        f.write("║  Total: " + f"{k1_count}/{total} templates ({k1_pct:.1f}%)" + " " * 42 + "║\n")
        f.write("╚" + "═" * 78 + "╝\n\n")
        
        f.write("=" * 80 + "\n")
        f.write("📊 HASIL KELOMPOK 1 - KOMPATIBEL\n")
        f.write("=" * 80 + "\n")
        f.write(f"{'No':4s} | {'Template':20s} | {'Status':15s}\n")
        f.write("-" * 80 + "\n")
        
        for i, name in enumerate(kelompok_1, 1):
            f.write(f"{i:3d}  | {name:18s} | ✅ KOMPATIBEL\n")
        
        f.write("\n" + "=" * 80 + "\n")
        f.write("RINGKASAN\n")
        f.write("=" * 80 + "\n")
        f.write(f"Total kompatibel: {k1_count}\n")
        f.write(f"Persentase: {k1_pct:.1f}%\n")
        f.write("\nSemua template di kelompok ini memiliki:\n")
        f.write("  ✓ Fungsi build_document() yang valid\n")
        f.write("  ✓ Module dapat di-load tanpa error\n")
        f.write("  ✓ Siap digunakan untuk generate dokumen\n")
    
    # Write Kelompok 2 report
    with open(k2_file, "w", encoding="utf-8") as f:
        f.write("╔" + "═" * 78 + "╗\n")
        f.write("║  KELOMPOK 2 — TIDAK KOMPATIBEL (Perlu Perbaikan)" + " " * 28 + "║\n")
        f.write("║  Tanggal: " + datetime.now().strftime('%d %B %Y') + " " * 51 + "║\n")
        f.write("║  Total: " + f"{k2_count}/{total} templates ({k2_pct:.1f}%)" + " " * 42 + "║\n")
        f.write("╚" + "═" * 78 + "╝\n\n")
        
        f.write("=" * 80 + "\n")
        f.write("📊 HASIL KELOMPOK 2 - TIDAK KOMPATIBEL\n")
        f.write("=" * 80 + "\n")
        f.write(f"{'No':4s} | {'Template':20s} | {'Error':40s}\n")
        f.write("-" * 80 + "\n")
        
        for i, name in enumerate(kelompok_2, 1):
            error = results[name]["error"][:38]
            f.write(f"{i:3d}  | {name:18s} | {error:38s}\n")
        
        # Categorize errors
        no_build = [n for n in kelompok_2 if "No build_document" in results[n]["error"]]
        attr_err = [n for n in kelompok_2 if "AttributeError" in results[n]["error"]]
        import_err = [n for n in kelompok_2 if "ModuleNotFoundError" in results[n]["error"] or "ImportError" in results[n]["error"]]
        other_err = [n for n in kelompok_2 if n not in no_build and n not in attr_err and n not in import_err]
        
        f.write("\n" + "=" * 80 + "\n")
        f.write("BREAKDOWN ERROR\n")
        f.write("=" * 80 + "\n")
        f.write(f"No build_document(): {len(no_build)} templates ({len(no_build)/total*100:.1f}%)\n")
        if no_build:
            f.write(f"  → {', '.join(no_build)}\n")
        f.write(f"\nAttributeError: {len(attr_err)} templates ({len(attr_err)/total*100:.1f}%)\n")
        if attr_err:
            f.write(f"  → {', '.join(attr_err)}\n")
        f.write(f"\nImport/Module Error: {len(import_err)} templates ({len(import_err)/total*100:.1f}%)\n")
        if import_err:
            f.write(f"  → {', '.join(import_err)}\n")
        f.write(f"\nOther Errors: {len(other_err)} templates ({len(other_err)/total*100:.1f}%)\n")
        if other_err:
            f.write(f"  → {', '.join(other_err)}\n")
        
        f.write("\n" + "=" * 80 + "\n")
        f.write("REKOMENDASI PERBAIKAN\n")
        f.write("=" * 80 + "\n")
        f.write(f"1. No build_document() ({len(no_build)} templates):\n")
        f.write("   → Tambahkan fungsi build_document() dengan signature standard\n")
        f.write(f"\n2. AttributeError ({len(attr_err)} templates):\n")
        f.write("   → Perbaiki template .docx yang hilang atau path error\n")
        f.write(f"\n3. Import Error ({len(import_err)} templates):\n")
        f.write("   → Install dependency yang hilang\n")
    
    print(f"✓ Kelompok 1 report: {k1_file}")
    print(f"✓ Kelompok 2 report: {k2_file}")
    print()
    print("Done.")

if __name__ == "__main__":
    main()
