import re, shutil
from pathlib import Path

JOURNAL_DIR = Path("/home/sirobo/papergenerator/backend/tools/Journal")

SKIP = {"AEJ", "AMORI", "IJECE"}  # Already have OMML

# Target all *gen.py files
for genpy in sorted(JOURNAL_DIR.glob("*gen.py")):
    name = genpy.stem.replace("gen", "")
    if name in SKIP:
        continue
    
    docx = JOURNAL_DIR / f"{name}.docx"
    if not docx.exists():
        continue  # Skip meta templates without docx
    
    code = genpy.read_text()
    
    # Skip if already has OMML (latex2mathml import in add_formula area)
    if "latex2mathml" in code:
        print(f"{name}: already has OMML, skip")
        continue
    
    # Find add_formula function and determine how it gets latex + number
    # Pattern varies: add_formula(doc, formula_data) or add_formula(doc, fm)
    # We need to preserve the function signature and the data extraction
    # Strategy: find add_formula, keep the data extraction lines, replace the body
    
    # Make backup
    bak = genpy.with_suffix(".py.omm_backup")
    shutil.copy2(genpy, bak)
    
    # Check what the function signature is
    if "def add_formula(doc, formula_data):" in code:
        old_sig = "def add_formula(doc, formula_data):"
        new_body = """    # OMML via shared utility
    import sys
    from pathlib import Path as _Path
    _jdir = _Path(__file__).resolve().parent
    if str(_jdir) not in sys.path:
        sys.path.insert(0, str(_jdir))
    from _formula_omml import add_omml_formula

    latex = str(formula_data.get("latex", formula_data.get("Formula", ""))).strip()
    number = str(formula_data.get("FormulaNumber", "")).strip()
    if not latex:
        return
    add_omml_formula(doc, latex, number, CFG, before_pt=4, after_pt=4,
                     alignment="center", font_body=CFG.get("font_body", "Times New Roman"),
                     size_body=CFG.get("size_body", 10))"""
    elif "def add_formula(doc, fm):" in code:
        old_sig = "def add_formula(doc, fm):"
        new_body = """    import sys
    from pathlib import Path as _Path
    _jdir = _Path(__file__).resolve().parent
    if str(_jdir) not in sys.path:
        sys.path.insert(0, str(_jdir))
    from _formula_omml import add_omml_formula

    latex = str(fm.get("latex", fm.get("Formula", ""))).strip()
    number = str(fm.get("FormulaNumber", "")).strip()
    if not latex:
        return
    add_omml_formula(doc, latex, number, CFG, before_pt=4, after_pt=4,
                     alignment="center", font_body=CFG.get("font_body", "Times New Roman"),
                     size_body=CFG.get("size_body", 10))"""
    elif "def add_formula_block(doc, fm):" in code:
        old_sig = "def add_formula_block(doc, fm):"
        new_body = """    import sys
    from pathlib import Path as _Path
    _jdir = _Path(__file__).resolve().parent
    if str(_jdir) not in sys.path:
        sys.path.insert(0, str(_jdir))
    from _formula_omml import add_omml_formula

    latex = str(fm.get("latex", fm.get("Formula", ""))).strip()
    number = str(fm.get("FormulaNumber", "")).strip()
    if not latex:
        return
    add_omml_formula(doc, latex, number, CFG, before_pt=4, after_pt=4,
                     alignment="center", font_body=CFG.get("font_body", "Times New Roman"),
                     size_body=CFG.get("size_body", 10))"""
    else:
        print(f"  {name}: add_formula signature unknown, skip")
        continue
    
    # Find the old function - from signature to next top-level def
    pattern = re.escape(old_sig) + r'(.*?)(?=^\S|\Z)'
    match = re.search(pattern, code, re.MULTILINE | re.DOTALL)
    if not match:
        print(f"  {name}: pattern not found, skip")
        continue
    
    old_body = match.group(1)
    new_func = old_sig + "\n" + new_body + "\n"
    
    new_code = code.replace(match.group(0), new_func)
    genpy.write_text(new_code)
    print(f"  {name}: PATCHED")

print("\nDone!")