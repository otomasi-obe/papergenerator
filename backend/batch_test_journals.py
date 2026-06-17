#!/usr/bin/env python3
"""
Batch test semua journal generator di tools/Journal/
- Copy _template.json lengkap → tools/Journal/
- Loop semua *gen.py → panggil build_document() atau generate()
- Simpan output → tools/Journal/output_testing/{JOURNAL}_output.docx
- Run auto_checker per journal
- Print summary
"""

import importlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
JOURNAL_DIR = BACKEND / "tools" / "Journal"
TEMPLATE_JSON = JOURNAL_DIR / "_template.json"
OUTPUT_DIR = JOURNAL_DIR / "output_testing"
CHECKER_SCRIPT = Path("/home/sirobo/ANNABIL/Project Papergenerator_Annabil/papergenerator/backend/template/A FIX/A Script/auto_checker.py")

# All 39 journal templates (based on .docx ori files)
JOURNALS = [
    "AEJ", "AMORI", "CCJ", "CERiMRE", "DJLIT", "EASR", "ELCTRICES", "ELKOLIND",
    "ENERGIUPM", "El-Usrah", "ICET", "ICIMECE", "ICONIE", "ICOSEG", "IJB",
    "IJECE", "IJEECS", "IJIMS", "IJITEE", "IJRED", "IJT", "JAMRIS", "JAT",
    "JCEF", "JEEMECS", "JIEB", "JMEM", "JNTETI", "JOKI", "JRC", "JTMM",
    "JTRANSIENT", "JTUNDIP", "KKCK", "MEV", "ROTASI", "UITM", "ULTIMACOMP",
    "IEEE",
]

# Add backend to sys.path
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Also add Journal dir for relative imports inside gen.py
if str(JOURNAL_DIR) not in sys.path:
    sys.path.insert(0, str(JOURNAL_DIR))


def _available_journals():
    codes = []
    for docx_path in sorted(JOURNAL_DIR.glob("*.docx")):
        code = docx_path.stem
        gen_path = JOURNAL_DIR / f"{code}gen.py"
        if gen_path.exists():
            codes.append(code)
    return sorted(set(codes), key=str.lower)


def _get_builder(journal_code):
    """Return (canonical, builder_fn) for a journal code."""
    available = _available_journals()
    m = {c.lower(): c for c in available}
    canonical = m.get(journal_code.lower())
    if not canonical:
        raise ValueError(f"Unknown journal: {journal_code}")

    mod = importlib.import_module(f"tools.Journal.{canonical}gen")
    builder = getattr(mod, "build_document", None)
    if callable(builder):
        return canonical, builder

    gen_fn = getattr(mod, "generate", None)
    if callable(gen_fn):
        return canonical, _make_adapter(mod, gen_fn)

    raise ValueError(f"No build_document or generate in {canonical}gen")


INPUT_NAMES = ("TEMPLATE_JSON", "JSON_PATH", "INPUT_JSON", "DATA_JSON")
OUTPUT_NAMES = ("OUTPUT_DOCX", "OUTPUT_PATH", "OUT_DOCX", "OUTPUT")


def _make_adapter(mod, gen_fn):
    """Adapt legacy generate() to build_document(json_path, output_path) interface."""
    def adapter(json_path, output_path):
        saved = {}
        in_name = next((n for n in INPUT_NAMES if hasattr(mod, n)), None)
        out_name = next((n for n in OUTPUT_NAMES if hasattr(mod, n)), None)
        if in_name:
            saved[in_name] = getattr(mod, in_name)
            setattr(mod, in_name, Path(json_path))
        if out_name:
            saved[out_name] = getattr(mod, out_name)
            if output_path:
                setattr(mod, out_name, Path(output_path))
        try:
            gen_fn()
        finally:
            for k, v in saved.items():
                setattr(mod, k, v)
        if output_path:
            return Path(output_path)
        return Path(getattr(mod, out_name)) if out_name else None
    return adapter


def run_generate(journal_code, json_path, output_path):
    """Generate DOCX for a journal. Returns (success, error_msg)."""
    try:
        canonical, builder = _get_builder(journal_code)
        result = builder(str(json_path), str(output_path))
        if output_path.exists():
            return True, None
        else:
            return False, f"Output file not created: {output_path}"
    except Exception as e:
        tb = traceback.format_exc(limit=3)
        return False, f"{type(e).__name__}: {e}\n{tb}"


def run_checker(template_path, output_path):
    """Run auto_checker. Returns (score, status, details)."""
    try:
        result = subprocess.run(
            [sys.executable, str(CHECKER_SCRIPT), str(template_path), str(output_path)],
            capture_output=True, text=True, timeout=60,
            cwd=str(CHECKER_SCRIPT.parent),
        )
        stdout = result.stdout
        # Parse score line
        score = 0
        status = "ERROR"
        for line in stdout.split("\n"):
            if "SKOR KECOCOKAN" in line:
                # [SKOR KECOCOKAN: 95%] -> STATUS: OK
                import re
                m = re.search(r"(\d+)%", line)
                if m:
                    score = int(m.group(1))
                m2 = re.search(r"STATUS:\s*(.+)", line)
                if m2:
                    status = m2.group(1).strip()
                break
        return score, status, stdout
    except subprocess.TimeoutExpired:
        return 0, "TIMEOUT", "Checker timed out after 60s"
    except Exception as e:
        return 0, "ERROR", str(e)


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    if not TEMPLATE_JSON.exists():
        print(f"ERROR: _template.json not found at {TEMPLATE_JSON}")
        sys.exit(1)

    if not CHECKER_SCRIPT.exists():
        print(f"ERROR: auto_checker.py not found at {CHECKER_SCRIPT}")
        sys.exit(1)

    # Use the rich _template.json we created
    json_path = TEMPLATE_JSON

    results = []

    print(f"\n{'='*70}")
    print(f"  BATCH TEST: {len(JOURNALS)} journal generators")
    print(f"  JSON: {json_path.name}")
    print(f"  Output: {OUTPUT_DIR}")
    print(f"  Checker: {CHECKER_SCRIPT.name}")
    print(f"{'='*70}\n")

    for i, journal in enumerate(JOURNALS, 1):
        template_docx = JOURNAL_DIR / f"{journal}.docx"
        output_docx = OUTPUT_DIR / f"{journal}_output.docx"

        print(f"[{i:2d}/{len(JOURNALS)}] {journal:15s} ", end="", flush=True)

        # Check template exists
        if not template_docx.exists():
            print(f"SKIP (no {journal}.docx)")
            results.append((journal, "SKIP", 0, "No template .docx"))
            continue

        # Generate
        t0 = time.time()
        ok, err = run_generate(journal, json_path, output_docx)
        elapsed = time.time() - t0

        if not ok:
            print(f"FAIL gen ({elapsed:.1f}s): {str(err)[:60]}")
            results.append((journal, "GEN_FAIL", 0, str(err)[:100]))
            continue

        # Checker
        score, status, checker_output = run_checker(template_docx, output_docx)
        print(f"OK gen ({elapsed:.1f}s) → Checker: {score}% ({status})")
        results.append((journal, "OK", score, status))

        # Save checker report
        report_path = OUTPUT_DIR / f"{journal}_audit.txt"
        report_path.write_text(checker_output, encoding="utf-8")

    # Summary
    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    print(f"{'Journal':<15s} {'Status':<10s} {'Score':>6s}  {'Detail'}")
    print(f"{'-'*60}")

    ok_count = 0
    fail_count = 0
    skip_count = 0

    for journal, status, score, detail in sorted(results):
        if status == "OK":
            ok_count += 1
            marker = "✅" if score >= 80 else "⚠️" if score >= 50 else "❌"
        elif status == "SKIP":
            skip_count += 1
            marker = "⏭️"
        else:
            fail_count += 1
            marker = "💥"
        print(f"{marker} {journal:<13s} {status:<10s} {score:>5d}%  {detail[:40]}")

    print(f"\n{'='*70}")
    print(f"  Total: {len(results)} | OK: {ok_count} | Gen Fail: {fail_count} | Skip: {skip_count}")

    # Score distribution
    scores = [s for _, st, s, _ in results if st == "OK"]
    if scores:
        avg = sum(scores) / len(scores)
        high = sum(1 for s in scores if s >= 80)
        mid = sum(1 for s in scores if 50 <= s < 80)
        low = sum(1 for s in scores if s < 50)
        print(f"  Score avg: {avg:.1f}% | >=80%: {high} | 50-79%: {mid} | <50%: {low}")

    print(f"{'='*70}\n")

    # Save summary JSON
    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "json_used": str(json_path),
        "results": [
            {"journal": j, "status": st, "score": sc, "detail": d}
            for j, st, sc, d in results
        ],
    }
    summary_path = OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Summary saved: {summary_path}")


if __name__ == "__main__":
    main()
