#!/usr/bin/env python3
"""Test PDF preview for all 49 journals via API."""
import subprocess, json, sys, time
from pathlib import Path

BACKEND = "http://127.0.0.1:8001"

# Generate JWT + get first paper info
result = subprocess.run(
    ['.venv/bin/python', '-c', '''
import sys, os, json
sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)
os.environ["WERKZEUG_RUN_MAIN"] = "true"
from main import app
from utils.database.models import Paper
from flask_jwt_extended import create_access_token
with app.app_context():
    paper = Paper.query.first()
    token = create_access_token(identity=str(15))
    info = {
        "id": paper.id,
        "title": paper.data.get("title", "") if paper.data else "",
        "journal": paper.data.get("journal", "IEEE") if paper.data else "IEEE"
    }
    print(token + "|||SPLIT|||" + json.dumps(info), flush=True)
'''],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    cwd='/home/sirobo/papergenerator/backend',
)

raw = result.stdout.strip()
if '|||SPLIT|||' not in raw:
    print(f"ERROR: no split found. stdout={raw[:200]!r}")
    sys.exit(1)

token, info_raw = raw.split('|||SPLIT|||')
paper_info = json.loads(info_raw)
print(f"Paper: {paper_info['id']} | Journal: {paper_info['journal']} | Title: {paper_info['title'][:40]}...")
print(f"Token: {token[:20]}...\n")

JOURNALS = sorted([
    "IEEE", "ACM", "Elsevier", "Springer", "MDPI", "APA",
    "DJLIT", "EASR", "ELCTRICES", "CCJ", "AEJ", "AMORI",
    "CERiMRE", "ELKOLIND", "ENERGIUPM", "El-Usrah", "ICET",
    "ICIMECE", "ICONIE", "ICOSEG", "IJB", "IJECE", "IJEECS",
    "IJIMS", "IJITEE", "IJRED", "IJT", "JAMRIS", "JAT",
    "JCEF", "JEEMECS", "JIEB", "JMEM", "JNTETI", "JOKI",
    "JRC", "JTMM", "JTRANSIENT", "JTUNDIP", "KKCK",
    "MEV", "Murhum", "Obsesi", "PAUDIA", "PGPAUDTrunojoyo",
    "PST", "ROTASI", "UITM", "ULTIMACOMP"
])

ok, fail = 0, []
for j in JOURNALS:
    payload = json.dumps({"journal": j})
    r = subprocess.run(
        ['curl', '-s', '-X', 'POST',
         f'{BACKEND}/api/papers/{paper_info["id"]}/pdf-preview',
         '-H', f'Authorization: Bearer {token}',
         '-H', 'Content-Type: application/json',
         '-d', payload,
         '--max-time', '60'],
        capture_output=True, text=True, timeout=65
    )
    try:
        resp = json.loads(r.stdout.strip())
        if resp.get('pdf_url'):
            print(f"  ✅ {j:20s} OK")
            ok += 1
        else:
            err = resp.get('error', r.stdout[:100])
            print(f"  ❌ {j:20s} FAIL — {err}")
            fail.append((j, err))
    except json.JSONDecodeError:
        print(f"  ❌ {j:20s} FAIL — non-JSON: {r.stdout[:100]}")
        fail.append((j, r.stdout[:100]))

print(f"\n{'='*60}")
print(f"TOTAL: {len(JOURNALS)} | OK: {ok} | FAIL: {len(fail)}")
if fail:
    print("\nFailed journals:")
    for j, e in fail:
        print(f"  ❌ {j}: {e}")
