import sys, os, glob
sys.path.insert(0, ".")
from pathlib import Path

# Nuke all caches
for m in list(sys.modules):
    if 'AMORI' in m or 'amori' in m.lower() or 'Journal' in str(m):
        del sys.modules[m]

for f in glob.glob("tools/Journal/__pycache__/AMORI*"):
    os.remove(f)

# Import
from tools.Journal import AMORIgen

# Debug patches
original_add_figure = AMORIgen.add_figure
def debug_add_figure(doc, fig_data, fig_counter):
    print(f"  DEBUG add_figure #{fig_counter}: Title={str(fig_data.get('Title','?'))[:30]}, Path={str(fig_data.get('Path','?'))[:40]}")
    path_exists = Path(str(fig_data.get('Path',''))).exists()
    print(f"    has_latex={'$' in str(fig_data.get('Title',''))}, Path_exists={path_exists}")
    return original_add_figure(doc, fig_data, fig_counter)
AMORIgen.add_figure = debug_add_figure

original_add_formula = AMORIgen.add_formula
def debug_add_formula(doc, formula_data):
    latex = str(formula_data.get("latex", ""))
    print(f"  DEBUG add_formula: latex={latex[:40]}")
    result = original_add_formula(doc, formula_data)
    print(f"    OMML attempted")
    return result
AMORIgen.add_formula = debug_add_formula

original_add_table = AMORIgen.add_table_element
def debug_add_table(doc, tbl_data, tbl_counter):
    title = str(tbl_data.get("Title", ""))
    print(f"  DEBUG add_table_element #{tbl_counter}: Title={title[:30]}, rows={len(tbl_data.get('Rows',[]))}")
    return original_add_table(doc, tbl_data, tbl_counter)
AMORIgen.add_table_element = debug_add_table

# Run
AMORIgen.TEMPLATE_JSON = Path("tools/Journal/_template.json")
AMORIgen.generate()
print("DONE")