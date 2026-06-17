#!/usr/bin/env python3
"""
Comprehensive test of all 44 journal DOCX template exports.
Checks:
1. Template DOCX file exists and is valid
2. Generator file has build_document function
3. All placeholder fields are correctly mapped (title, authors, abstract, sections, references)
"""

import json
import os
import sys
import traceback
import zipfile
from pathlib import Path

# Use uv's python
sys.path.insert(0, str(Path(__file__).parent))

JOURNAL_DIR = Path(__file__).parent
RESULTS = []

# Expected placeholder fields that should be mapped in each generator
EXPECTED_FIELDS = ['title', 'author', 'abstract', 'keyword', 'section', 'reference', 'content']

def check_docx_valid(docx_path: Path) -> dict:
    """Check if DOCX file is valid and extract text content."""
    result = {"exists": False, "valid": False, "size": 0, "text_content": "", "styles": []}
    
    if not docx_path.exists():
        return result
    
    result["exists"] = True
    result["size"] = docx_path.stat().st_size
    
    if result["size"] == 0:
        return result
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zf:
            # Check it's a valid ZIP
            bad = zf.testzip()
            if bad:
                result["error"] = f"Corrupt entry: {bad}"
                return result
            
            # Check required DOCX components
            names = zf.namelist()
            has_document_xml = 'word/document.xml' in names
            has_content_types = '[Content_Types].xml' in names
            
            if not has_document_xml:
                result["error"] = "Missing word/document.xml"
                return result
            if not has_content_types:
                result["error"] = "Missing [Content_Types].xml"
                return result
            
            result["valid"] = True
            
            # Extract text content from document.xml
            import re
            doc_xml = zf.read('word/document.xml').decode('utf-8', errors='replace')
            # Extract text between <w:t> tags
            texts = re.findall(r'<w:t[^>]*>(.*?)</w:t>', doc_xml)
            result["text_content"] = ' '.join(texts)
            
            # Extract styles
            if 'word/styles.xml' in names:
                styles_xml = zf.read('word/styles.xml').decode('utf-8', errors='replace')
                style_ids = re.findall(r'w:styleId="([^"]+)"', styles_xml)
                result["styles"] = style_ids
            
    except zipfile.BadZipFile:
        result["error"] = "Not a valid ZIP/DOCX file"
    except Exception as e:
        result["error"] = str(e)
    
    return result


def check_generator(gen_path: Path) -> dict:
    """Check if generator file has required functions and field mappings."""
    result = {
        "exists": False,
        "has_build_document": False,
        "has_template_path": False,
        "template_path_value": None,
        "fields_referenced": [],
        "missing_fields": [],
        "import_errors": [],
    }
    
    if not gen_path.exists():
        return result
    
    result["exists"] = True
    
    try:
        content = gen_path.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        result["error"] = f"Cannot read file: {e}"
        return result
    
    # Check for build_document function
    if 'def build_document(' in content:
        result["has_build_document"] = True
    
    # Check for TEMPLATE_PATH reference
    import re
    template_match = re.search(r'TEMPLATE_PATH\s*=\s*(.+)', content)
    if template_match:
        result["has_template_path"] = True
        result["template_path_value"] = template_match.group(1).strip()
    
    # Check which expected fields are referenced in the generator
    # Look for common patterns: paper_data["title"], data.get("title"), json["title"] etc.
    field_patterns = {
        'title': r'["\']title["\']|TITLE',
        'author': r'["\']author|["\']authors|AUTHOR',
        'abstract': r'["\']abstract|ABSTRACT',
        'keyword': r'["\']keyword|KEYWORD|Index Terms',
        'section': r'["\']sections?|["\']heading|["\']body|SECTION',
        'reference': r'["\']references?|["\']bibliography|REFERENCE',
        'content': r'["\']content|["\']body|["\']paragraphs|CONTENT',
    }
    
    for field, pattern in field_patterns.items():
        if re.search(pattern, content, re.IGNORECASE):
            result["fields_referenced"].append(field)
        else:
            result["missing_fields"].append(field)
    
    return result


def check_placeholders_in_docx(docx_path: Path) -> dict:
    """Check what placeholder text exists in the DOCX template."""
    result = {"placeholders_found": [], "placeholder_mapping": {}}
    
    if not docx_path.exists():
        return result
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zf:
            import re
            doc_xml = zf.read('word/document.xml').decode('utf-8', errors='replace')
            texts = re.findall(r'<w:t[^>]*>(.*?)</w:t>', doc_xml)
            full_text = ' '.join(texts)
            
            # Common placeholder patterns used in templates
            placeholder_patterns = {
                'title_placeholder': [r'\[.*?[Tt]itle.*?\]', r'\{.*?[Tt]itle.*?\}', r'TITLE', r'Paper Title'],
                'author_placeholder': [r'\[.*?[Aa]uthor.*?\]', r'\{.*?[Aa]uthor.*?\}', r'AUTHOR', r'Author Name'],
                'abstract_placeholder': [r'\[.*?[Aa]bstract.*?\]', r'\{.*?[Aa]bstract.*?\}', r'ABSTRACT', r'Abstract text'],
                'keyword_placeholder': [r'\[.*?[Kk]eyword.*?\]', r'\{.*?[Kk]eyword.*?\}', r'KEYWORD', r'Index Terms'],
                'content_placeholder': [r'\[.*?[Cc]ontent.*?\]', r'\[.*?[Bb]ody.*?\]', r'Lorem ipsum', r'CONTENT'],
                'reference_placeholder': [r'\[.*?[Rr]eference.*?\]', r'\{.*?[Rr]eference.*?\}', r'REFERENCE', r'Bibliography'],
            }
            
            for placeholder_type, patterns in placeholder_patterns.items():
                for pattern in patterns:
                    matches = re.findall(pattern, full_text)
                    if matches:
                        result["placeholders_found"].append({
                            "type": placeholder_type,
                            "matches": matches[:3]  # limit to first 3
                        })
                        break
            
            # Also check for style-based placeholders (common in academic templates)
            style_placeholders = []
            for text in texts:
                text_stripped = text.strip()
                if text_stripped and len(text_stripped) > 2:
                    # Check for common placeholder-like text
                    if any(kw in text_stripped.lower() for kw in ['title', 'author', 'abstract', 'keyword', 'index term']):
                        style_placeholders.append(text_stripped[:100])
            
            result["style_placeholders"] = style_placeholders[:10]
            
    except Exception as e:
        result["error"] = str(e)
    
    return result


def test_all_templates():
    """Run all tests on all 44 templates."""
    
    # Get all generator files
    gen_files = sorted(JOURNAL_DIR.glob("*gen.py"))
    
    print("=" * 80)
    print("JOURNAL DOCX TEMPLATE EXPORT TEST REPORT")
    print("=" * 80)
    print(f"\nTotal generator files found: {len(gen_files)}")
    
    all_results = []
    failures = []
    warnings = []
    
    for gen_path in gen_files:
        code = gen_path.stem.replace('gen', '')
        docx_path = JOURNAL_DIR / f"{code}.docx"
        
        print(f"\n{'─' * 60}")
        print(f"  Template: {code}")
        print(f"{'─' * 60}")
        
        template_result = {
            "code": code,
            "gen_file": gen_path.name,
            "docx_file": docx_path.name,
            "checks": {}
        }
        
        # 1. Check DOCX file
        docx_check = check_docx_valid(docx_path)
        template_result["checks"]["docx_valid"] = docx_check
        
        if docx_check["exists"]:
            if docx_check["valid"]:
                print(f"  ✅ DOCX exists and is valid ({docx_check['size']:,} bytes)")
            else:
                msg = f"  ❌ DOCX exists but INVALID: {docx_check.get('error', 'unknown')}"
                print(msg)
                failures.append(f"{code}: {msg}")
        else:
            # Check for sample_paper variant
            sample_path = JOURNAL_DIR / f"sample_paper_{code}.docx"
            if sample_path.exists():
                print(f"  ⚠️  {docx_path.name} MISSING, but sample_paper_{code}.docx exists")
                warnings.append(f"{code}: Template DOCX missing (sample_paper_{code}.docx available as fallback)")
                # Check the sample instead
                docx_check = check_docx_valid(sample_path)
                template_result["checks"]["docx_valid_fallback"] = docx_check
                template_result["checks"]["docx_valid"]["fallback_used"] = str(sample_path.name)
            else:
                msg = f"  ❌ DOCX file MISSING: {docx_path.name}"
                print(msg)
                failures.append(f"{code}: Template DOCX file missing ({docx_path.name})")
        
        # 2. Check generator
        gen_check = check_generator(gen_path)
        template_result["checks"]["generator"] = gen_check
        
        if gen_check["has_build_document"]:
            print(f"  ✅ Generator has build_document()")
        else:
            msg = f"  ❌ Generator MISSING build_document() function"
            print(msg)
            failures.append(f"{code}: Missing build_document() in {gen_path.name}")
        
        if gen_check["missing_fields"]:
            msg = f"  ⚠️  Generator may not handle fields: {', '.join(gen_check['missing_fields'])}"
            print(msg)
            if 'title' in gen_check["missing_fields"] or 'abstract' in gen_check["missing_fields"]:
                warnings.append(f"{code}: Missing field handling - {', '.join(gen_check['missing_fields'])}")
        
        # 3. Check placeholders in DOCX
        if docx_check["exists"] and docx_check["valid"]:
            placeholder_check = check_placeholders_in_docx(docx_path)
            template_result["checks"]["placeholders"] = placeholder_check
            
            if placeholder_check["placeholders_found"]:
                print(f"  ✅ Placeholders found: {len(placeholder_check['placeholders_found'])} types")
                for ph in placeholder_check["placeholders_found"]:
                    print(f"      - {ph['type']}: {ph['matches']}")
            else:
                # Check if template uses style-based approach (no text placeholders)
                content = docx_check.get("text_content", "")
                if content:
                    print(f"  ℹ️  No explicit placeholders (uses style-based filling)")
                else:
                    msg = f"  ⚠️  No placeholders found in template DOCX"
                    print(msg)
                    warnings.append(f"{code}: No placeholders found in DOCX template")
        
        # 4. Check that TEMPLATE_PATH in gen file matches actual file
        if gen_check["has_template_path"]:
            tp_val = gen_check["template_path_value"]
            # Resolve the path
            if 'BASE_DIR' in tp_val:
                expected_name = tp_val.split('"')[1] if '"' in tp_val else tp_val.split("'")[1] if "'" in tp_val else ""
                expected_path = JOURNAL_DIR / expected_name
                path_exists = expected_path.exists()
                if not path_exists:
                    msg = f"  ❌ TEMPLATE_PATH references '{expected_name}' which does NOT exist"
                    print(msg)
                    failures.append(f"{code}: TEMPLATE_PATH points to non-existent file: {expected_name}")
                else:
                    print(f"  ✅ TEMPLATE_PATH -> {expected_name} (exists)")
            template_result["checks"]["template_path_resolved"] = path_exists if 'expected_name' in dir() else None
        
        all_results.append(template_result)
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"\nTotal templates tested: {len(all_results)}")
    
    # Count passes
    fully_ok = 0
    partial_ok = 0
    fully_broken = 0
    
    for r in all_results:
        code = r["code"]
        docx_ok = r["checks"].get("docx_valid", {}).get("valid", False) or r["checks"].get("docx_valid_fallback", {}).get("valid", False)
        gen_ok = r["checks"].get("generator", {}).get("has_build_document", False)
        
        if docx_ok and gen_ok:
            fully_ok += 1
        elif docx_ok or gen_ok:
            partial_ok += 1
        else:
            fully_broken += 1
    
    print(f"\n✅ Fully OK (DOCX valid + generator has build_document): {fully_ok}")
    print(f"⚠️  Partial OK (one check passed): {partial_ok}")
    print(f"❌ Fully broken: {fully_broken}")
    
    if failures:
        print(f"\n{'─' * 40}")
        print(f"FAILURES ({len(failures)}):")
        print(f"{'─' * 40}")
        for f in failures:
            print(f"  ❌ {f}")
    
    if warnings:
        print(f"\n{'─' * 40}")
        print(f"WARNINGS ({len(warnings)}):")
        print(f"{'─' * 40}")
        for w in warnings:
            print(f"  ⚠️  {w}")
    
    # Detailed per-template results table
    print(f"\n{'─' * 40}")
    print("DETAILED RESULTS:")
    print(f"{'─' * 40}")
    print(f"{'Template':<20} {'DOCX':<8} {'Valid':<8} {'build_doc':<12} {'Fields OK':<30}")
    print(f"{'─' * 78}")
    
    for r in all_results:
        code = r["code"]
        docx = r["checks"].get("docx_valid", {})
        fallback = r["checks"].get("docx_valid_fallback", {})
        gen = r["checks"].get("generator", {})
        
        docx_exists = "✅" if docx.get("exists") or fallback.get("exists") else "❌"
        docx_valid = "✅" if docx.get("valid") or fallback.get("valid") else "❌"
        has_build = "✅" if gen.get("has_build_document") else "❌"
        
        missing = gen.get("missing_fields", [])
        if missing:
            fields_status = f"⚠️ missing: {', '.join(missing)}"
        else:
            fields_status = "✅ all mapped"
        
        print(f"  {code:<18} {docx_exists:<8} {docx_valid:<8} {has_build:<12} {fields_status}")
    
    # Save full results as JSON
    output_path = JOURNAL_DIR / "template_test_results.json"
    with open(output_path, 'w') as f:
        json.dump({
            "total_templates": len(all_results),
            "fully_ok": fully_ok,
            "partial_ok": partial_ok,
            "fully_broken": fully_broken,
            "failures": failures,
            "warnings": warnings,
            "results": all_results
        }, f, indent=2, default=str)
    
    print(f"\n📄 Full results saved to: {output_path}")
    print(f"\n{'=' * 80}")
    
    return len(failures) == 0


if __name__ == "__main__":
    success = test_all_templates()
    sys.exit(0 if success else 1)
