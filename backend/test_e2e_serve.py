#!/usr/bin/env python3
"""End-to-end test: generate PDF + serve it with Authorization header."""
import subprocess, json

# Get token + paper info
r1 = subprocess.run(
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
    print(token + "|||" + paper.id + "|||" + (paper.data.get("title","") if paper.data else ""), flush=True)
'''],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd='/home/sirobo/papergenerator/backend'
)
parts = r1.stdout.strip().split('|||')
token, paper_id, title = parts[0], parts[1], parts[2]
print(f"Paper: {paper_id[:10]}... | Title: {title[:40]}")

# Step 1: POST to generate PDF
payload = json.dumps({'journal': 'IEEE'})
r2 = subprocess.run(
    ['curl', '-s', '-X', 'POST',
     f'http://127.0.0.1:8001/api/papers/{paper_id}/pdf-preview',
     '-H', f'Authorization: Bearer {token}',
     '-H', 'Content-Type: application/json',
     '-d', payload,
     '--max-time', '60'],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=65
)
resp = json.loads(r2.stdout.strip())
print(f"POST: {resp}")
pdf_url = resp.get('pdf_url', '')

# Step 2: GET the PDF with Authorization header
url = 'http://127.0.0.1:8001' + pdf_url
r3 = subprocess.run(
    ['curl', '-s', '-D', '-', url,
     '-H', f'Authorization: Bearer {token}',
     '--max-time', '10'],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15
)
# Split headers from body (binary)
raw = r3.stdout
header_end = raw.find(b'\r\n\r\n')
if header_end < 0:
    header_end = raw.find(b'\n\n')
if header_end >= 0:
    headers = raw[:header_end].decode('utf-8', errors='replace')
    body = raw[header_end + (4 if raw[header_end:header_end+4] == b'\r\n\r\n' else 2):]
    print("HEADERS:")
    for l in headers.split('\n'):
        print(f"  {l}")
    print(f"BODY: {body[:4]!r} (len={len(body)})")
    if body[:4] == b'%PDF':
        print("✅ PDF served correctly!")
    else:
        print(f"❌ Expected %PDF, got {body[:4]!r}")
else:
    print(f"Raw: {raw[:50]!r}")
