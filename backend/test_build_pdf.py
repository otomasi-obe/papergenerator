#!/usr/bin/env python3
"""Test build_pdf for all 49 journal generators.

Usage: python3 test_build_pdf.py [JOURNAL_CODE]
  Without args: tests all 49 journals
  With arg: tests only the specified journal
"""

import importlib
import json
import sys
import time
from pathlib import Path

JOURNAL_DIR = Path(__file__).parent / "tools" / "Journal"
TEST_JSON = {
    "title": "Test Paper Title For PDF Generation",
    "abstract": "This is a test abstract for PDF generation testing.",
    "keywords": ["test", "pdf", "generation"],
    "authors": [
        {
            "name": "Test Author",
            "affiliation": "Test University",
            "email": "test@test.com"
        }
    ],
    "section1": {
        "title": "Introduction",
        "content": [
            {"id": "text", "text": "This is the introduction section of the test paper."}
        ]
    },
    "section2": {
        "title": "Methodology",
        "content": [
            {"id": "text", "text": "This is the methodology section with test content."}
        ]
    },
    "section3": {
        "title": "Results",
        "content": [
            {"id": "text", "text": "This is the results section with test content."}
        ]
    },
    "section4": {
        "title": "Conclusion",
        "content": [
            {"id": "text", "text": "This is the conclusion section."}
        ]
    },
    "references": [
        {"text": "Author A, \"Title of Paper,\" Journal, vol. 1, pp. 1-10, 2024."},
        {"text": "Author B, \"Another Paper,\" Conference, pp. 20-30, 2023."}
    ],
    "figures": [],
    "tables": []
}

def get_journal_codes():
    codes = []
    for p in JOURNAL_DIR.glob("*gen.py"):
        if p.name.startswith("_"):
            continue
        code = p.stem[:-3]
        if code:
            codes.append(code)
    return sorted(codes, key=str.lower)


def test_journal_pdf(code: str, tmp_dir: Path) -> tuple[bool, str]:
    """Test build_pdf for one journal. Returns (success, message)."""
    try:
        mod = importlib.import_module(f"tools.Journal.{code}gen")
        mod = importlib.reload(mod)
    except Exception as e:
        return False, f"import failed: {e}"

    build_pdf = getattr(mod, "build_pdf", None)
    if not callable(build_pdf):
        return False, "no build_pdf function"

    json_path = tmp_dir / f"_{code}_test.json"
    pdf_path = tmp_dir / f"_{code}_test.pdf"

    try:
        json_path.write_text(json.dumps(TEST_JSON, ensure_ascii=False, indent=2), encoding="utf-8")
        t0 = time.time()
        build_pdf(json_path=json_path, pdf_path=pdf_path)
        dt = time.time() - t0

        if not pdf_path.exists():
            return False, "pdf not created"
        
        size = pdf_path.stat().st_size
        if size < 100:
            return False, f"pdf too small ({size} bytes)"

        # Check PDF header
        with open(pdf_path, "rb") as f:
            header = f.read(4)
        if header != b"%PDF":
            return False, f"invalid PDF header: {header!r}"

        return True, f"OK ({size:,} bytes, {dt:.1f}s)"
    except Exception as e:
        return False, f"build_pdf error: {e}"
    finally:
        json_path.unlink(missing_ok=True)
        pdf_path.unlink(missing_ok=True)


def main():
    import tempfile

    codes = get_journal_codes()
    filter_code = sys.argv[1] if len(sys.argv) > 1 else None
    if filter_code:
        codes = [c for c in codes if c.lower() == filter_code.lower()]
        if not codes:
            print(f"Journal {filter_code!r} not found")
            return 1

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        ok = 0
        fail = 0
        results = []

        for code in codes:
            success, msg = test_journal_pdf(code, tmp_dir)
            status = "✅" if success else "❌"
            results.append((code, status, msg))
            if success:
                ok += 1
            else:
                fail += 1
            print(f"  {status} {code:20s} {msg}")

        print(f"\n{'='*60}")
        print(f"Total: {len(codes)} | OK: {ok} | FAIL: {fail}")
        
        if fail > 0:
            print("\nFailed journals:")
            for code, status, msg in results:
                if status == "❌":
                    print(f"  {code}: {msg}")
        
        return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
