#!/usr/bin/env python3
"""
Mass-patch generator files with 6 fixes:
1. _remove_trailing_empty_sectpr_paras: zero-width support
2. _clean_latex in add_figure (title, prompt_hint)
3. _clean_latex in add_table_element (title, headers, rows)
4. _clean_latex in add_formula (formula, label)
5. Heading color #943634
6. _inject_masthead_content for masthead tables

Usage: python3 mass_patch.py
"""

import re
from pathlib import Path

PROD_DIR = Path('/home/sirobo/papergenerator/backend/tools/Journal')
EXCLUDE = {'AEJgen'}  # AEJ already patched


def patch_sectpr_remove(content: str) -> str:
    """Patch 1: zero-width support in _remove_trailing_empty_sectpr_paras."""
    old = 'if not txt or txt == "\\u200b":'
    new = 'if not txt or all(c == \'\\u200B\' for c in txt):'
    if old in content:
        content = content.replace(old, new)
        print("  [1] sectpr: zero-width fix applied")
    else:
        print("  [1] sectpr: pattern not found (skip)")
    return content


def patch_clean_latex_figure(content: str) -> str:
    """Patch 2: add _clean_latex to add_figure/add_figure_block title and prompt_hint."""
    if '_clean_latex' not in content:
        print("  [2] _clean_latex function missing (skip)")
        return content
    
    # Find add_figure or add_figure_block function
    m = re.search(r'(def add_figure(?:_block)?\(.*?\n.*?def |\Z)', content, re.DOTALL)
    if not m:
        print("  [2] add_figure/add_figure_block not found (skip)")
        return content
    
    func_body = m.group(1)
    
    # Check if already has _clean_latex on title/prompt
    if '_clean_latex(title' in func_body or '_clean_latex(prompt' in func_body:
        print("  [2] figure: already patched")
        return content
    
    # Find title assignment
    new_body = re.sub(
        r'(title\s*=\s*)(.+?)(\n\s*#|\n\s*if|\n\s*for|\n\s*add_prompt|\Z)',
        r'\1_clean_latex(\2)\3',
        func_body, count=1
    )
    
    # Find prompt_hint assignment
    new_body = re.sub(
        r'(prompt_hint\s*=\s*)(.+?)(\n\s*#|\n\s*if|\n\s*for|\n\s*add_prompt|\Z)',
        r'\1_clean_latex(\2)\3',
        new_body, count=1
    )
    
    if new_body != func_body:
        content = content.replace(func_body, new_body)
        print("  [2] figure: _clean_latex added")
    else:
        print("  [2] figure: pattern not found (skip)")
    return content


def patch_clean_latex_table(content: str) -> str:
    """Patch 3: add _clean_latex to add_table_element/add_table_block."""
    if '_clean_latex' not in content:
        return content
    
    m = re.search(r'(def add_table(?:_element|_block)?\(.*?\n.*?def |\Z)', content, re.DOTALL)
    if not m:
        return content
    
    func_body = m.group(1)
    if '_clean_latex(title' in func_body:
        print("  [3] table: already patched")
        return content
    
    # Find title assignment
    new_body = re.sub(
        r'(title\s*=\s*)(.+?)(\n\s*#|\n\s*if|\n\s*for|\n\s*headers|\Z)',
        r'\1_clean_latex(\2)\3',
        func_body, count=1
    )
    
    if new_body != func_body:
        content = content.replace(func_body, new_body)
        print("  [3] table: _clean_latex added")
    return content


def patch_clean_latex_formula(content: str) -> str:
    """Patch 4: add _clean_latex to add_formula/add_formula_block."""
    if '_clean_latex' not in content:
        return content
    
    m = re.search(r'(def add_formula(?:_block)?\(.*?\n.*?def |\Z)', content, re.DOTALL)
    if not m:
        return content
    
    func_body = m.group(1)
    if '_clean_latex(formula' in func_body or '_clean_latex(latex' in func_body:
        print("  [4] formula: already patched")
        return content
    
    # Find formula/latex assignment
    new_body = re.sub(
        r'((?:formula|latex)\s*=\s*)(.+?)(\n\s*#|\n\s*if|\n\s*add_formula|\Z)',
        r'\1_clean_latex(\2)\3',
        func_body, count=1
    )
    
    if new_body != func_body:
        content = content.replace(func_body, new_body)
        print("  [4] formula: _clean_latex added")
    return content


def patch_heading_color(content: str) -> str:
    """Patch 5: add heading color #943634."""
    if 'heading_color' in content or '943634' in content:
        print("  [5] heading color: already present")
        return content
    
    # Find set_run_font call in add_heading/add_section_heading
    m = re.search(r'(def (?:add_section_heading|add_heading)\(.*?\n.*?def |\Z)', content, re.DOTALL)
    if not m:
        print("  [5] heading function not found (skip)")
        return content
    
    func_body = m.group(1)
    
    # Find set_run_font call
    new_body = re.sub(
        r'(set_run_font\([^)]*?)(\))',
        r'\1, color=(0x94, 0x36, 0x34)\2',
        func_body, count=1
    )
    
    if new_body != func_body:
        content = content.replace(func_body, new_body)
        print("  [5] heading color: added")
    return content


def patch_inject_masthead(content: str) -> str:
    """Patch 6: add _inject_masthead_content for masthead tables."""
    if '_inject_masthead' in content:
        print("  [6] inject masthead: already present")
        return content
    
    # Check if file has masthead table patterns
    has_table = 'def add_table' in content or 'add_table_element' in content
    
    # Check for generate() function
    gen_match = re.search(r'(def generate\(.*?\nif __name__|$)', content, re.DOTALL)
    if not gen_match:
        print("  [6] generate() not found (skip)")
        return content
    
    gen_body = gen_match.group(1)
    
    # Find title block generation area
    # Look for "add_title(doc, data)" or similar
    if 'add_title(doc, data)' in gen_body:
        # Insert _inject_masthead_content before add_title
        new_body = gen_body.replace(
            'add_title(doc, data)',
            '# Masthead inject\n    _inject_masthead_content(doc, data)\n    # add_title(doc, data) — replaced by inject'
        )
        if new_body != gen_body:
            content = content.replace(gen_body, new_body)
            print("  [6] inject masthead: added")
    else:
        print("  [6] inject masthead: no add_title pattern (skip)")
    
    return content


def main():
    gens = sorted([f for f in PROD_DIR.glob('*gen.py') if f.stem not in EXCLUDE])
    print(f"Mass-patching {len(gens)} generators...\n")
    
    for gen in gens:
        print(f"\n=== {gen.stem} ===")
        with open(gen, 'rb') as f:
            content = f.read().decode('utf-8')
        
        original = content
        content = patch_sectpr_remove(content)
        content = patch_clean_latex_figure(content)
        content = patch_clean_latex_table(content)
        content = patch_clean_latex_formula(content)
        content = patch_heading_color(content)
        content = patch_inject_masthead(content)
        
        if content != original:
            with open(gen, 'wb') as f:
                f.write(content.encode('utf-8'))
            print(f"  SAVED: {gen.name}")
        else:
            print("  No changes needed")
    
    print(f"\nDone. Patched {len(gens)} generators.")


if __name__ == '__main__':
    main()
