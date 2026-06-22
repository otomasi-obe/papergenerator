import json, os, sys
from pathlib import Path

os.chdir("/home/sirobo/papergenerator/backend")
IMAGES_DIR = Path("user/anabilhisyam23/c689a97227d0/image")
JP = Path("tools/Journal/_template.json")

d = json.loads(JP.read_text())

def fix_paths(obj, depth=0):
    if isinstance(obj, dict):
        if obj.get("id") == "gambar":
            fname = Path(str(obj.get("Path", ""))).name
            if fname:
                full = IMAGES_DIR / fname
                if full.exists():
                    obj["Path"] = str(full)
        for k, v in obj.items():
            fix_paths(v, depth+1)
    elif isinstance(obj, list):
        for item in obj:
            fix_paths(item, depth)

fix_paths(d)
JP.write_text(json.dumps(d, ensure_ascii=False, indent=2))
print("JSON paths fixed")

# Verify
d2 = json.loads(JP.read_text())
def verify(obj):
    if isinstance(obj, dict):
        if obj.get("id") == "gambar":
            p = Path(obj.get("Path", ""))
            if not p.is_absolute():
                print(f"  WARN: Still relative: {p}")
            else:
                print(f"  OK: {p}")
        for k, v in obj.items():
            verify(v)
    elif isinstance(obj, list):
        for item in obj:
            verify(item)
verify(d2)
print("Done")