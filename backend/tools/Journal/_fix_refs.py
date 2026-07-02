"""
Fix all journal generators to handle references.items format and structured ref dicts.
Run with: python3 _fix_refs.py
Skips: JTUNDIPgen.py, KKCKgen.py (already fixed).
"""
import re
import os
import glob

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

FORMAT_REFERENCE_FN = '''
def _format_reference(item) -> str:
    """Format a reference dict into a citation string."""
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return str(item).strip()
    text = item.get("text") or item.get("Text") or item.get("value")
    if text:
        return str(text).strip()
    parts = []
    authors = item.get("authors", [])
    if authors:
        parts.append(", ".join(str(a) for a in authors) if isinstance(authors, list) else str(authors))
    year = item.get("year")
    if year:
        parts.append(f"({year})")
    title = item.get("title", "")
    if title:
        parts.append(f\'"{title},"\')
    jname = item.get("journal") or item.get("conference") or ""
    if jname:
        parts.append(str(jname) + ",")
    vol = item.get("volume", "")
    if vol:
        parts.append(f"vol. {vol},")
    issue = item.get("issue", "")
    if issue:
        parts.append(f"no. {issue},")
    pages = item.get("pages", "")
    if pages:
        parts.append(f"pp. {pages},")
    doi = item.get("doi", "")
    if doi:
        parts.append(f"doi: {doi}.")
    url = item.get("url", "")
    if url:
        accessed = item.get("accessed", "")
        parts.append(f"[Online]. Available: {url}" + (f" [Accessed: {accessed}]." if accessed else "."))
    publisher = item.get("publisher", "")
    if publisher and not jname:
        location = item.get("location", "")
        parts.append(f"{location}: {publisher}." if location else f"{publisher}.")
    result = " ".join(str(p) for p in parts if p).strip()
    result = result.replace(" , ", ", ").replace(" .", ".")
    if result.endswith(","):
        result = result[:-1] + "."
    if not result.endswith("."):
        result = result + "."
    return result

'''

SKIP = {"JTUNDIPgen.py", "KKCKgen.py"}

# Pattern groups for "simple style" - one of several common patterns:
# Pattern A: dict only checks "content"
# refs_data.get("content", [])
# Pattern B: just refs.get("content") or []
# Pattern C: inline .get("content", []) or .get("content") or []

def has_format_ref(content):
    """Any form of _format_ref* or _format_reference or _format_structured_ref."""
    return bool(re.search(r'def _format_ref', content))

def has_items_handling(content):
    """True if 'items' is already in the refs extraction path."""
    # Check specifically near reference extraction, not just any items
    return bool(re.search(r'\.get\(["\']items["\']', content))

def add_format_ref_before_first_def(content):
    """Insert _format_reference before the first `def ` at module level after imports."""
    # Find a good insertion point: first top-level def
    match = re.search(r'^def ', content, re.MULTILINE)
    if match:
        pos = match.start()
        return content[:pos] + FORMAT_REFERENCE_FN.lstrip('\n') + content[pos:]
    # Fallback: append before last line
    return content + FORMAT_REFERENCE_FN

# ── Pattern matchers & fixers ─────────────────────────────────────────────────

def fix_simple_content_only(content, filename):
    """
    Fix pattern:
        refs_data.get("content", [])
    in a block like:
        if isinstance(refs_data, dict):
            refs_list = refs_data.get("content", [])
        elif isinstance(refs_data, list):
            refs_list = refs_data
        else:
            refs_list = []
    Replace with items-aware extraction.
    Also fix inline dict text extraction: ref.get("text", ...) → _format_reference(ref)
    """
    changed = False

    # Fix dict-based extraction to also check items
    def replace_content_get(m):
        nonlocal changed
        changed = True
        return m.group(0).replace(
            '.get("content", [])',
            '.get("content") or refs_data.get("items") or []'
        ).replace(
            ".get('content', [])",
            ".get('content') or refs_data.get('items') or []"
        )

    # Generic: refs_data.get("content", [])
    new_content, n = re.subn(
        r'refs_list\s*=\s*refs_data\.get\("content",\s*\[\]\)',
        'refs_list = refs_data.get("content") or refs_data.get("items") or []',
        content
    )
    if n:
        content = new_content
        changed = True

    # refs_data.get('content', [])
    new_content, n = re.subn(
        r"refs_list\s*=\s*refs_data\.get\('content',\s*\[\]\)",
        "refs_list = refs_data.get('content') or refs_data.get('items') or []",
        content
    )
    if n:
        content = new_content
        changed = True

    return content, changed


def fix_generic_pattern(content):
    """
    Fix any remaining dict.get("content", []) patterns specifically in the reference extraction.
    Works for many generator styles.
    """
    changed = False

    # ICETgen style:  refs.get("content", [])  in add_references
    # AEJgen/AMORIgen: refs_data.get("content", []) → already handled above by simple pattern
    # EASRgen: items = refs_block.get("content") or []
    # ELCTRICESgen: content = references.get("content", [])
    # JEEMECSgen: items = references.get("content", []) if isinstance(references, dict) else references
    # Springergen/APAgen/Elseviergen/MDPIgen: references = references.get("content", [])
    # CCJgen: items = refs.get("content", []) or []
    # JAMRISgen: references = list(_refs_raw.get("content", []))
    # IJBgen/IJECEgen: ref_content = ref_data.get("content", [])
    # JATgen: ref_content = ref_data.get("content", [])
    # JIEBgen: ref_content = ref_data.get("content", [])
    # JMEMgen: items = list(references.get("content", []) or [])
    # JOKIgen: content = refs.get("content", [])
    # JRCgen: references = config["references"].get("content", [])
    # MEVgen: already handles items
    # Murhumgen/PGPAUDTrunojoyogen/Obsesigen: refs.get("content", []) if isinstance(refs, dict)
    # UITMgen: items = refs.get("content") or [...]
    # ULTIMACOMPgen: content = refs_cfg.get("content", [])
    # El-Usrahgen: refs_content = refs_data.get("content", [])
    # ENERGIUPMgen/ICIMECEgen/ICONIEgen/ICOSEGgen/ELKOLINDgen/IJIMSgen/IJEECSgen/PSTgen/DJLITgen/CERiMREgen:
    #   refs_list = refs_data.get("content", [])  → handled by simple pattern
    # IJITEEgen/IJREDgen: inline list comp with refs.get("content") 
    # IJTgen: inline refs.get("content") in two places
    # JCEFgen: items = refs.get("content") or [...]
    # JTRANSIENTgen: handled separately

    return content, changed


# ── Per-file fixers ───────────────────────────────────────────────────────────

def fix_refs_extraction_items(content, var_names=None):
    """
    Fix patterns where a variable gets set via .get("content", [...]).
    Replaces them with a form that also checks "items".
    var_names: optional list of variable names to restrict replacements.
    """
    changed = False

    patterns = [
        # refs_list = refs_data.get("content", [])
        (r'(refs_list\s*=\s*refs_data\.get\()("content")(\s*,\s*\[\])',
         r'\1"content") or refs_data.get("items") or []',
         True),
        # refs_list = refs_data.get('content', [])
        (r"(refs_list\s*=\s*refs_data\.get\()('content')(\s*,\s*\[\])",
         r"\1'content') or refs_data.get('items') or []",
         True),
        # ref_content = ref_data.get("content", [])
        (r'(ref_content\s*=\s*ref_data\.get\()("content")(\s*,\s*\[\])',
         r'\1"content") or ref_data.get("items") or []',
         True),
        # ref_content = ref_data.get('content', [])
        (r"(ref_content\s*=\s*ref_data\.get\()('content')(\s*,\s*\[\])",
         r"\1'content') or ref_data.get('items') or []",
         True),
        # content = refs_cfg.get("content", [])
        (r'(content\s*=\s*refs_cfg\.get\()("content")(\s*,\s*\[\])',
         r'\1"content") or refs_cfg.get("items") or []',
         True),
        # items = references.get("content", []) if isinstance(...) else references
        # → items = (references.get("content") or references.get("items") or []) if isinstance(...) else references
        (r'(items\s*=\s*)references\.get\("content",\s*\[\]\)(\s*if\s*isinstance)',
         r'\1(references.get("content") or references.get("items") or [])\2',
         True),
        # items = refs.get("content", []) or []
        (r'items\s*=\s*refs\.get\("content",\s*\[\]\)\s*or\s*\[\]',
         'items = refs.get("content") or refs.get("items") or []',
         True),
        # items = refs.get("content") or []
        (r'items\s*=\s*refs\.get\("content"\)\s*or\s*\[\]',
         'items = refs.get("content") or refs.get("items") or []',
         True),
        # references = references.get("content", [])  (APAgen/Springergen/Elseviergen/MDPIgen)
        (r'references\s*=\s*references\.get\("content",\s*\[\]\)',
         'references = references.get("content") or references.get("items") or []',
         True),
        # references = list(_refs_raw.get("content", []))  (JAMRISgen)
        (r'references\s*=\s*list\(_refs_raw\.get\("content",\s*\[\]\)\)',
         'references = list(_refs_raw.get("content") or _refs_raw.get("items") or [])',
         True),
        # refs_list = refs_data.get("content", ...) + or
        # refs_list = refs_data.get("content", ...)  with no fallback
        # items = list(references.get("content", []) or [])  (JMEMgen)
        (r'items\s*=\s*list\(references\.get\("content",\s*\[\]\)\s*or\s*\[\]\)',
         'items = list(references.get("content") or references.get("items") or [])',
         True),
        # refs_content = refs_data.get("content", [])  (El-Usrahgen)
        (r'refs_content\s*=\s*refs_data\.get\("content",\s*\[\]\)',
         'refs_content = refs_data.get("content") or refs_data.get("items") or []',
         True),
        # content = refs.get("content", [])  (JOKIgen, ELCTRICESgen)
        (r'(content\s*=\s*refs(?:_block)?\.get\()("content")(\s*,\s*\[\])',
         r'\1"content") or refs.get("items") or []',
         True),
        # items = refs_block.get("content") or []  (EASRgen)
        (r'(items\s*=\s*refs_block\.get\()("content"\))\s*or\s*\[\]',
         r'\1"content") or refs_block.get("items") or []',
         True),
        # content = references.get("content", [])  (ELCTRICESgen, JEEMECSgen references dict)
        (r'(content\s*=\s*)references\.get\("content",\s*\[\]\)',
         r'\1references.get("content") or references.get("items") or []',
         True),
        # rl = refs.get("content", [])  (PAUDIAgen old format)
        (r'rl\s*=\s*refs\.get\("content",\s*\[\]\)',
         'rl = refs.get("content") or refs.get("items") or []',
         True),
        # rl = refs.get("content", []) if isinstance(refs, dict) else ...  (Obsesigen/Murhumgen/PGPAUDTrunojoyogen)
        (r'rl\s*=\s*refs\.get\("content",\s*\[\]\)\s*if\s*isinstance\(refs,\s*dict\)',
         'rl = (refs.get("content") or refs.get("items") or []) if isinstance(refs, dict)',
         True),
        # refs_list = refs.get("content", []) if isinstance(refs, dict)  (Obsesigen)
        (r'refs_list\s*=\s*refs\.get\("content",\s*\[\]\)\s*if\s*isinstance\(refs,\s*dict\)',
         'refs_list = (refs.get("content") or refs.get("items") or []) if isinstance(refs, dict)',
         True),
        # references = config["references"].get("content", [])  (JRCgen dict branch)
        (r'references\s*=\s*config\["references"\]\.get\("content",\s*\[\]\)',
         'references = config["references"].get("content") or config["references"].get("items") or []',
         True),
        # references = config[...].get("content", [])  (JRCgen section_references branch)
        (r'references\s*=\s*config\["section_references"\]\.get\("content",\s*\[\]\)',
         'references = config["section_references"].get("content") or config["section_references"].get("items") or []',
         True),
        # title = str(references.get("title", "References")) → keep; also items
        # items = refs.get("content") or [...]  (UITMgen/JCEFgen)
        # UITMgen: items = refs.get("content") or [...]  → already returns items list, just need items key
    ]

    for pat, repl, do_it in patterns:
        if not do_it:
            continue
        new_content, n = re.subn(pat, repl, content)
        if n:
            content = new_content
            changed = True

    return content, changed


def fix_ref_dict_text_access(content):
    """
    Replace inline dict text extraction with _format_reference(ref) call.
    Patterns like:
        ref.get("text", ref) if isinstance(ref, dict) else ref
        ref.get("text", "") if isinstance(ref, dict) else str(ref)
        str(ref.get("text", ref) if isinstance(ref, dict) else ref).strip()
        (r.get("text") or r.get("Text") or "").strip() if isinstance(r, dict) else str(r)
    """
    changed = False

    replacements = [
        # AEJgen/AMORIgen/ELKOLINDgen/ICIMECEgen etc:
        # ref_text = str(ref.get("text", ref) if isinstance(ref, dict) else ref).strip()
        (r'ref_text\s*=\s*str\(ref\.get\("text",\s*ref\)\s*if\s*isinstance\(ref,\s*dict\)\s*else\s*ref\)\.strip\(\)',
         'ref_text = _format_reference(ref)'),
        # ref_text = str(ref.get("text", ref) if isinstance(ref, dict) else ref)
        (r'ref_text\s*=\s*str\(ref\.get\("text",\s*ref\)\s*if\s*isinstance\(ref,\s*dict\)\s*else\s*ref\)',
         'ref_text = _format_reference(ref)'),
        # Elseviergen/APAgen: ref_text = ref.get("text", "")  (inside isinstance dict block)
        # IJECEgen/IJBgen/JATgen/JIEBgen:
        # ref_text = ref.get("text", "") if isinstance(ref, dict) else str(ref)
        (r'ref_text\s*=\s*ref\.get\("text",\s*""\)\s*if\s*isinstance\(ref,\s*dict\)\s*else\s*str\(ref\)',
         'ref_text = _format_reference(ref)'),
        # CERiMREgen/DJLITgen/ELKOLINDgen/IJEECSgen/IJIMSgen/ICIMECEgen/ICONIEgen/ICOSEGgen/ENERGIUPMgen/PSTgen:
        # ref_text = ref.get("text", str(ref)) if isinstance(ref, dict) else str(ref)
        (r'ref_text\s*=\s*ref\.get\("text",\s*str\(ref\)\)\s*if\s*isinstance\(ref,\s*dict\)\s*else\s*str\(ref\)',
         'ref_text = _format_reference(ref)'),
        # JAMRISgen: text = str(reference.get("text") or "").strip()  (in loop)
        (r'text\s*=\s*str\(reference\.get\("text"\)\s*or\s*""\)\.strip\(\)',
         'text = _format_reference(reference)'),
        # IJITEEgen/IJREDgen/IJTgen inline list comp:
        # items = [((r.get("text") or r.get("Text") or "").strip() if isinstance(r, dict) else str(r)) for r in (refs.get("content") or [])]
        (r'items\s*=\s*\[\(\(r\.get\("text"\)\s*or\s*r\.get\("Text"\)\s*or\s*""\)\.strip\(\)\s*if\s*isinstance\(r,\s*dict\)\s*else\s*str\(r\)\)\s*for\s*r\s*in\s*\(refs\.get\("content"\)\s*or\s*\[\]\)\]',
         'items = [_format_reference(r) for r in (refs.get("content") or refs.get("items") or [])]'),
        # IJTgen second occurrence (ref_raw):
        (r'ref_items\s*=\s*\[\(\(r\.get\("text"\)\s*or\s*r\.get\("Text"\)\s*or\s*""\)\.strip\(\)\s*if\s*isinstance\(r,\s*dict\)\s*else\s*str\(r\)\)\s*for\s*r\s*in\s*\(ref_raw\.get\("content"\)\s*or\s*\[\]\)\]',
         'ref_items = [_format_reference(r) for r in (ref_raw.get("content") or ref_raw.get("items") or [])]'),
        # JTRANSIENTgen:
        (r'items\s*=\s*\[\(\(it\.get\("text"\)\s*or\s*it\.get\("Text"\)\s*or\s*""\)\.strip\(\)\s*if\s*isinstance\(it,\s*dict\)\s*else\s*str\(it\)\)\.strip\(\)\s*for\s*it\s*in\s*references_raw\]',
         'items = [_format_reference(it) for it in references_raw]'),
        # JCEFgen: text extraction in the loop
        # for inline: ref if isinstance(ref, dict) → use _format_reference
        # CCJgen: ref.get("text", str(ref)) if isinstance(ref, dict) else str(ref)
        (r'ref\.get\("text",\s*str\(ref\)\)\s*if\s*isinstance\(ref,\s*dict\)\s*else\s*str\(ref\)',
         '_format_reference(ref)'),
        # Obsesigen loop: ref.get("text", ref) if isinstance(ref, dict) else str(ref)
        (r'ref\.get\("text",\s*ref\)\s*if\s*isinstance\(ref,\s*dict\)\s*else\s*str\(ref\)',
         '_format_reference(ref)'),
        # Murhumgen/PGPAUDTrunojoyogen: text in loop
        # text = ref.get("text", str(ref)) ...
        (r'text\s*=\s*ref\.get\("text",\s*str\(ref\)\)',
         'text = _format_reference(ref)'),
        # JRCgen inline:
        (r'ref\.get\("text"\)\s*or\s*ref\.get\("Text"\)\s*or\s*str\(ref\)',
         '_format_reference(ref)'),
        # Elseviergen/APAgen: ref_text = ref.get("text", "")  in isinstance block
        (r'ref_text\s*=\s*ref\.get\("text",\s*""\)',
         'ref_text = _format_reference(ref)'),
        # Springergen: same
        # MDPIgen: same
        # EASRgen: ref_text = ref.get("text", str(ref)) if isinstance(ref, dict) else str(ref)
        # → already covered by pattern above
        # UITMgen: text = ref.get("text") or ref.get("Text") or str(ref)  if isinstance
        (r'text\s*=\s*ref\.get\("text"\)\s*or\s*ref\.get\("Text"\)\s*or\s*str\(ref\)',
         'text = _format_reference(ref)'),
        # JMEMgen: ref_text = r.get("text") or r.get("Text") or str(r)  (in loop)
        (r'ref_text\s*=\s*r\.get\("text"\)\s*or\s*r\.get\("Text"\)\s*or\s*str\(r\)',
         'ref_text = _format_reference(r)'),
        # MEVgen: references.append(r.get("text", r.get("Text", str(r))))
        (r'references\.append\(r\.get\("text",\s*r\.get\("Text",\s*str\(r\)\)\)\)',
         'references.append(_format_reference(r))'),
        # JTRANSIENTgen dict branch:
        (r'items\s*=\s*\[\(\(it\.get\("text"\)\s*or\s*it\.get\("Text"\)\s*or\s*""\)\.strip\(\)\s*if\s*isinstance\(it,\s*dict\)\s*else\s*str\(it\)\)\s*for\s*it\s*in\s*items_raw\]',
         'items = [_format_reference(it) for it in items_raw]'),
        # JNTETIgen:
        (r'\(item\.get\("text"\)\s*or\s*item\.get\("Text"\)\s*or\s*""\)\.strip\(\)',
         '_format_reference(item)'),
        # ICETgen:
        (r'ref_text\s*=\s*ref\.get\("text"\)\s*or\s*ref\.get\("Text"\)\s*or\s*str\(ref\)\s*if\s*isinstance\(ref,\s*dict\)\s*else\s*str\(ref\)',
         'ref_text = _format_reference(ref)'),
        # IJBgen: ref_text = ref.get("text", "") if isinstance  → handled above
        # Generic fallback  (isinstance(ref, dict) block with .get("text", "")):
        (r'if\s*isinstance\(ref,\s*dict\):\s*\n\s*ref_text\s*=\s*ref\.get\("text",\s*""\)\s*\n\s*else:\s*\n\s*ref_text\s*=\s*str\(ref\)',
         'ref_text = _format_reference(ref)'),
        # ELCTRICESgen: ref.get("text") or ref.get("Text") or str(ref)
        (r'ref\.get\("text"\)\s*or\s*ref\.get\("Text"\)\s*or\s*str\(ref\)',
         '_format_reference(ref)'),
    ]

    for pat, repl in replacements:
        new_content, n = re.subn(pat, repl, content)
        if n:
            content = new_content
            changed = True

    return content, changed


def process_file(filepath):
    name = os.path.basename(filepath)
    if name in SKIP:
        print(f"  SKIP {name}")
        return False

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    changed = False

    # 1. Fix items extraction
    content, c1 = fix_refs_extraction_items(content)
    if c1:
        changed = True

    # 2. Fix dict text access to use _format_reference
    content, c2 = fix_ref_dict_text_access(content)
    if c2:
        changed = True

    # 3. Add _format_reference function if needed (only if we actually use it now or file needs it)
    if changed or not has_format_ref(content):
        if not has_format_ref(content):
            content = add_format_ref_before_first_def(content)
            changed = True

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  FIXED {name}")
        return True
    else:
        print(f"  NOOP  {name}")
        return False


def main():
    gen_files = sorted(glob.glob(os.path.join(SCRIPT_DIR, '*gen.py')))
    fixed = []
    noop = []
    for f in gen_files:
        name = os.path.basename(f)
        if name in SKIP:
            print(f"  SKIP  {name}")
            continue
        result = process_file(f)
        (fixed if result else noop).append(name)

    print(f"\nFixed: {len(fixed)}, NoOp: {len(noop)}")
    if fixed:
        print("  Fixed:", ", ".join(fixed))


if __name__ == "__main__":
    main()
