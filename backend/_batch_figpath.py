import re, shutil
from pathlib import Path

JOURNAL_DIR = Path("/home/sirobo/papergenerator/backend/tools/Journal")

def has_image_embed(genpy):
    """Check if generator already embeds images (not just prompts)."""
    code = genpy.read_text()
    # If it has add_figure with add_picture or run.add_picture, it embeds
    return "add_picture" in code

def fix_add_figure(genpy):
    """Add alternative image path resolution before the first path check."""
    code = genpy.read_text()
    name = genpy.stem.replace("gen", "")
    
    # Backup
    bak = genpy.with_suffix(".py.fig_backup")
    shutil.copy2(genpy, bak)
    
    # Find the pattern: "if path_text:" or "if img_path:" and add alt resolution
    # Pattern 1: candidate = BASE / path_text
    # Pattern 2: full_path = BASE / img_path if img_path
    
    modified = False
    
    # Fix pattern 1: candidate = BASE / path_text
    pattern1 = r'(image_path\s*=\s*None\s*\n\s*if\s+path_text:\s*\n\s*candidate\s*=\s*BASE\s*/\s*path_text)'
    replacement1 = r'image_path = None\n    if path_text:\n        # Try multiple resolution strategies\n        for cand in [Path(path_text), BASE / path_text]:\n            if cand.is_file():\n                image_path = cand\n                break'
    
    new_code = re.sub(pattern1, replacement1, code)
    if new_code != code:
        modified = True
        code = new_code
    
    # Fix pattern 2: full_path = BASE / img_path ...        
    pattern2 = r'(full_path\s*=\s*BASE\s*/\s*img_path\s+if\s+img_path\s+else\s+None\s*\n\s*inserted\s*=\s*False\s*\n\s*if\s+full_path\s+and\s+full_path\.exists)'
    replacement2 = r'full_path = None\n    if img_path:\n        for cand in [Path(img_path), BASE / img_path]:\n            if cand.is_file():\n                full_path = cand\n                break\n    inserted = False\n    if full_path and full_path.exists'
    
    new_code2 = re.sub(pattern2, replacement2, code)
    if new_code2 != code:
        modified = True
        code = new_code2
    
    if modified:
        genpy.write_text(code)
        print(f"  {name}: FIG PATHS FIXED")
        return True
    return False

# Target generators that have image embedding already (not prompts)
TARGETS = ["JIEB", "JAT", "IJB", "ICET", "CCJ", "EASR"]

for t in TARGETS:
    genpy = JOURNAL_DIR / f"{t}gen.py"
    if not genpy.exists():
        print(f"  {t}: MISSING")
        continue
    
    if has_image_embed(genpy):
        fixed = fix_add_figure(genpy)
        if not fixed:
            print(f"  {t}: no pattern match, SKIP")
    else:
        print(f"  {t}: prompt-only, SKIP")

print("\nDone!")