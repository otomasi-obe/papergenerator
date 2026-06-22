import sys, os, glob
sys.path.insert(0, ".")
from pathlib import Path
import json

# Nuke ALL caches
for m in list(sys.modules):
    if any(x in str(m).lower() for x in ['amori', 'journal', 'tools']):
        del sys.modules[m]

# Delete all pyc files matching AMORI anywhere
import subprocess
subprocess.run(["find", "/home/sirobo/papergenerator/backend", "-name", "*AMORI*pyc", "-delete"])

# Now import
from tools.Journal import AMORIgen

# Override BEFORE any call
TEST_JSON = Path("/home/sirobo/papergenerator/backend/tools/Journal/_template.json").resolve()
AMORIgen.TEMPLATE_JSON = TEST_JSON
print(f"TEMPLATE_JSON after override: {AMORIgen.TEMPLATE_JSON}")

# Read directly
d = json.loads(TEST_JSON.read_text())
figs_in_json = 0
for k in sorted([k for k in d if k.startswith("section")]):
    for item in d[k].get("content", []):
        if item.get("type") == "figure":
            figs_in_json += 1
            print(f"  JSON section {k}: Path={item.get('Path','?')}")

# Now see what load_json returns
data = AMORIgen.load_json()
print(f"load_json() keys: {list(data.keys())[:10]}")
for k in sorted([k for k in data if k.startswith("section")])[:2]:
    for item in data[k].get("content", []):
        if item.get("type") == "figure":
            print(f"  DATA section {k}: Path={item.get('Path','?')}")