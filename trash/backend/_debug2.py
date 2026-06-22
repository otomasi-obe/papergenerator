import sys, os, glob, json
sys.path.insert(0, ".")
from pathlib import Path

# Nuke ALL caches
for m in list(sys.modules):
    if any(x in str(m).lower() for x in ['amori', 'journal', 'tools']):
        del sys.modules[m]
for root, dirs, files in os.walk("."):
    for d in dirs:
        if d == "__pycache__":
            for f in os.listdir(os.path.join(root, d)):
                if "AMORI" in f or "amori" in f:
                    os.remove(os.path.join(root, d, f))

from tools.Journal import AMORIgen
orig_process = AMORIgen.process_content_items

def debug_process(doc, content_list, fig_counter, tbl_counter):
    print(f"  process_content_items: {len(content_list)} items")
    for i, item in enumerate(content_list):
        if isinstance(item, dict):
            tid = str(item.get("id", ""))
            if tid in ("gambar", "image", "figure", "tabel", "table", "rumus", "equation", "formula"):
                print(f"    [{i}] id={tid} Path={str(item.get('Path',''))[:40]}")
    return orig_process(doc, content_list, fig_counter, tbl_counter)

AMORIgen.process_content_items = debug_process
AMORIgen.generate()
print("DONE")