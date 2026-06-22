#!/usr/bin/env python3
"""Generate paper 1 via generate-stream and save to file."""
import json, requests, sys

BASE = "http://localhost:8001"
PAPER_ID = sys.argv[1] if len(sys.argv) > 1 else "8ac27c5beb6e"
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/paper_output.json"
PROMPT = sys.argv[3] if len(sys.argv) > 3 else "Tulis paper SLR: AI dalam Media Pembelajaran Adaptif untuk Literasi Awal AUD"
KIND = sys.argv[4] if len(sys.argv) > 4 else "review"

resp = requests.post(f"{BASE}/api/auth/login", json={"email":"rofiqcp@gmail.com","password":"paper2026"})
token = resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

print(f"Starting generate-stream for {PAPER_ID}...", flush=True)
r = requests.post(
    f"{BASE}/api/papers/{PAPER_ID}/generate-stream",
    headers=headers,
    json={"prompt": PROMPT, "language": "id", "paper_kind": KIND, "generate_images": False},
    stream=True,
    timeout=600
)

last_event = ""
for line in r.iter_lines():
    if line:
        ls = line.decode('utf-8') if isinstance(line, bytes) else line
        if ls.startswith('event:'):
            last_event = ls.split(':', 1)[1].strip()
            if last_event == 'thinking' or last_event == 'content':
                print(".", end="", flush=True)
        elif ls.startswith('data:') and last_event == 'done':
            data = json.loads(ls[5:].strip())
            with open(OUTPUT, "w") as f:
                json.dump(data["paper"], f, indent=2, ensure_ascii=False)
            paper = data["paper"]
            print(f"\nDONE! Title: {paper.get('title','')[:80]}")
            print(f"Sections: {len(paper.get('sections',[]))} | Refs: {len(paper.get('references',[]))}")
            print(f"Saved to {OUTPUT}")
            sys.exit(0)

print("FAILED: no done event received")
sys.exit(1)