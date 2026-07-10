#!/usr/bin/env python3
"""Test all journal generators by loading them and running a minimal paper through."""

import sys, json, traceback
from pathlib import Path

# Minimal test paper
TEST_PAPER = {
    "title": "Test Paper Title",
    "authors": [{"name": "John Doe", "affiliation": "University X", "location": "City", "email": "j@example.com"}],
    "abstract": "This is a test abstract for the paper.",
    "keywords": ["test", "paper", "keyword"],
    "sections": [
        {"title": "Introduction", "content": [{"id": "text", "text": "Introduction content here."}]},
        {"title": "Methods", "content": [{"id": "text", "text": "Methods content here."}]},
        {"title": "Results", "content": [{"id": "text", "text": "Results content here."}]},
        {"title": "Conclusion", "content": [{"id": "text", "text": "Conclusion content here."}]},
    ],
    "references": [
        {"text": "[1] J. Doe, 'Test reference', 2024."}
    ],
    "journal": "IEEE",
    "language": "en",
}

def test_journals():
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from main import _get_builder_for_journal, _resolve_journal_code, _available_journals
    import tempfile

    available = _available_journals()
    results = {}
    for code in sorted(available):
        try:
            resolved = _resolve_journal_code(code)
            _, builder = _get_builder_for_journal(resolved)
            # Run builder with temp files
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as jf:
                json.dump(TEST_PAPER, jf)
                json_path = Path(jf.name)
            with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as of:
                out_path = Path(of.name)
            try:
                builder(json_path, out_path)
                if out_path.exists() and out_path.stat().st_size > 0:
                    results[code] = "OK"
                else:
                    results[code] = "FAIL: no output"
            except Exception as e:
                results[code] = f"FAIL: {e}"
            finally:
                json_path.unlink(missing_ok=True)
                out_path.unlink(missing_ok=True)
        except Exception as e:
            results[code] = f"LOAD FAIL: {e}"
    
    ok = fail = 0
    for code, status in sorted(results.items()):
        icon = "✅" if status == "OK" else "❌"
        print(f"  {icon} {code}: {status}")
        if status == "OK":
            ok += 1
        else:
            fail += 1
    print(f"\n  Summary: {ok} OK, {fail} FAIL ({ok+fail} total)")
    return fail == 0

if __name__ == "__main__":
    success = test_journals()
    sys.exit(0 if success else 1)
