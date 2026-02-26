#!/usr/bin/env python3
"""
Independent test script for Generate Full Paper with AI.

Usage:
  # Test via running backend server (default: http://localhost:5000):
  python test_generate_full.py

  # Test with a custom topic:
  python test_generate_full.py "Lane Detection using Deep Learning"

  # Test directly against OpenAI (no backend server needed):
  python test_generate_full.py --direct "Lane Detection using Deep Learning"

  # Use a different server URL:
  python test_generate_full.py --url http://localhost:5000 "My Topic"
"""

import sys
import os
import time
import json
import argparse
import re

# ─── Try to load .env from the same directory ───────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass  # python-dotenv not available; rely on environment variables


def test_via_server(base_url: str, topic: str) -> bool:
    """Test Generate Full Paper through the running backend server."""
    try:
        import requests
    except ImportError:
        print("[ERROR] 'requests' library not found. Install with: pip install requests")
        return False

    print(f"\n{'='*60}")
    print("TEST: Generate Full Paper with AI (via backend server)")
    print(f"Server : {base_url}")
    print(f"Topic  : {topic}")
    print(f"{'='*60}\n")

    # ── Step 0: Health check ────────────────────────────────────────────────
    print("[Step 0] Health check ...")
    try:
        r = requests.get(f"{base_url}/api/health", timeout=10)
        health = r.json()
        print(f"  Status  : {health.get('status')}")
        print(f"  Model   : {health.get('model')}")
        print(f"  API Key : {'✓ configured' if health.get('hasApiKey') else '✗ NOT configured'}")
        if not health.get("hasApiKey"):
            print("\n[ERROR] OPENAI_API_KEY is not configured in backend/.env")
            return False
    except Exception as e:
        print(f"  [ERROR] Cannot reach server: {e}")
        print("  Make sure the backend is running: cd backend && python app.py")
        return False

    # ── Step 1: Start generation job ────────────────────────────────────────
    print("\n[Step 1] Starting full paper generation job ...")
    try:
        r = requests.post(
            f"{base_url}/api/generate-full",
            json={"prompt": topic},
            timeout=20,
        )
        if r.status_code != 200:
            print(f"  [ERROR] HTTP {r.status_code}: {r.text[:300]}")
            return False
        data = r.json()
        job_id = data.get("job_id")
        if not job_id:
            print(f"  [ERROR] No job_id in response: {data}")
            return False
        print(f"  Job ID  : {job_id}")
        print(f"  Response: {data}")
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False

    # ── Step 2: Poll until done ──────────────────────────────────────────────
    print("\n[Step 2] Polling for result (max 15 minutes) ...")
    t_start = time.time()
    MAX_WAIT = 15 * 60  # 15 minutes
    poll_interval = 5   # seconds

    while True:
        time.sleep(poll_interval)
        elapsed = int(time.time() - t_start)
        mins, secs = divmod(elapsed, 60)
        time_str = f"{mins}m {secs}s" if mins else f"{secs}s"

        try:
            r = requests.get(f"{base_url}/api/job/{job_id}", timeout=15)
            poll_data = r.json()
        except Exception as e:
            print(f"  [{time_str}] Poll error (retrying): {e}")
            continue

        status = poll_data.get("status")
        print(f"  [{time_str}] Status: {status}", end="")

        if status == "done":
            paper = poll_data.get("paper", {})
            usage = poll_data.get("usage", {})
            print(f"  ✓  (elapsed={poll_data.get('elapsed', elapsed)}s)")
            print(f"\n{'='*60}")
            print("RESULT:")
            print(f"{'='*60}")
            print(f"  Title       : {paper.get('title', '(no title)')}")
            authors = paper.get("authors", [])
            print(f"  Authors     : {len(authors)} author(s)")
            for a in authors:
                print(f"               - {a.get('name')} <{a.get('email')}>")
            print(f"  Abstract    : {(paper.get('abstract',''))[:120]}...")
            print(f"  Keywords    : {paper.get('keywords', [])}")
            sections = paper.get("sections", [])
            print(f"  Sections    : {len(sections)}")
            for sec in sections:
                subsecs = sec.get("subsections", [])
                print(f"    {sec.get('number','?')}. {sec.get('title','?')} ({len(subsecs)} subsections)")
            print(f"  Figures     : {len(paper.get('figures', []))}")
            print(f"  Tables      : {len(paper.get('tables', []))}")
            print(f"  Equations   : {len(paper.get('equations', []))}")
            refs = paper.get("references", [])
            print(f"  References  : {len(refs)}")
            print(f"\n  Token usage : prompt={usage.get('prompt_tokens','?')}, "
                  f"completion={usage.get('completion_tokens','?')}, "
                  f"total={usage.get('total_tokens','?')}")
            print(f"\n  Full JSON preview (first 500 chars):")
            print(f"  {json.dumps(paper)[:500]}...")
            print(f"\n[SUCCESS] Paper generated in {time_str}")
            return True

        elif status == "error":
            err = poll_data.get("error", "Unknown error")
            timeout_flag = poll_data.get("timeout", False)
            print(f"\n[ERROR] Generation failed: {err}")
            if timeout_flag:
                print("  Hint: The OpenAI API timed out. Try a shorter/simpler topic.")
            return False

        elif status == "pending":
            server_elapsed = poll_data.get("elapsed", elapsed)
            print(f"  (server elapsed: {server_elapsed}s)")
        else:
            print(f"  Unknown status: {poll_data}")

        if elapsed > MAX_WAIT:
            print(f"\n[ERROR] Timed out waiting after {time_str}")
            return False


def test_direct_openai(topic: str) -> bool:
    """Test OpenAI API directly without a backend server (same logic as backend job)."""
    try:
        from openai import OpenAI
        import httpx
    except ImportError:
        print("[ERROR] openai library not found. Install with: pip install openai httpx")
        return False

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "sk-your-actual-api-key":
        print("[ERROR] OPENAI_API_KEY not set. Add it to backend/.env or export it.")
        return False

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    print(f"\n{'='*60}")
    print("TEST: Generate Full Paper with AI (direct OpenAI call)")
    print(f"Model  : {model}")
    print(f"Topic  : {topic}")
    print(f"{'='*60}\n")

    client = OpenAI(
        api_key=api_key,
        timeout=httpx.Timeout(connect=30.0, read=1200.0, write=60.0, pool=10.0),
        max_retries=0,
    )

    system_prompt = (
        "You are an expert IEEE conference paper author. "
        "Generate a complete IEEE conference paper as valid JSON only — "
        "no markdown, no text outside the JSON object."
    )
    user_message = f"""Generate a complete IEEE conference paper on: {topic}

Return ONLY a JSON object with keys:
title, authors (array with name/affiliation/location/email), abstract, keywords,
sections (array with id/number/title/content/subsections), acknowledgment,
references (array with id/text), figures, tables, equations.

Keep content concise but complete. Use IEEE citation format [1][2].
All LaTeX in JSON strings: double-escape backslashes (\\\\alpha, \\\\frac{{a}}{{b}}).
Inline math: $...$  |  Display: $$.$$
"""

    print("[Step 1] Calling OpenAI API (this may take 3-10 minutes) ...")
    t_start = time.time()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
    except Exception as e:
        elapsed = int(time.time() - t_start)
        print(f"[ERROR] OpenAI API call failed after {elapsed}s: {e}")
        return False

    elapsed = int(time.time() - t_start)
    usage = response.usage
    print(f"[Step 1] Done in {elapsed}s | tokens: {usage.total_tokens}")

    result_text = response.choices[0].message.content.strip()

    # Strip markdown fences
    if result_text.startswith("```"):
        result_text = re.sub(r'^```(?:json)?\s*', '', result_text)
        result_text = re.sub(r'\s*```$', '', result_text.rstrip())

    print("\n[Step 2] Parsing JSON response ...")
    try:
        paper = json.loads(result_text)
    except json.JSONDecodeError as e:
        print(f"  Direct parse failed: {e}. Trying brace extraction ...")
        first = result_text.find('{')
        last = result_text.rfind('}')
        if first != -1 and last > first:
            try:
                paper = json.loads(result_text[first:last + 1])
            except json.JSONDecodeError as e2:
                print(f"  [ERROR] JSON extraction also failed: {e2}")
                print(f"  Raw response (first 500 chars): {result_text[:500]}")
                return False
        else:
            print(f"  [ERROR] No JSON object found in response")
            print(f"  Raw response (first 500 chars): {result_text[:500]}")
            return False

    print(f"\n{'='*60}")
    print("RESULT:")
    print(f"{'='*60}")
    print(f"  Title       : {paper.get('title', '(no title)')}")
    authors = paper.get("authors", [])
    print(f"  Authors     : {len(authors)} author(s)")
    for a in authors:
        print(f"               - {a.get('name')} <{a.get('email')}>")
    abstract = paper.get("abstract", "")
    print(f"  Abstract    : {abstract[:120]}...")
    print(f"  Keywords    : {paper.get('keywords', [])}")
    sections = paper.get("sections", [])
    print(f"  Sections    : {len(sections)}")
    for sec in sections:
        subsecs = sec.get("subsections", [])
        print(f"    {sec.get('number','?')}. {sec.get('title','?')} ({len(subsecs)} subsections)")
    print(f"  Figures     : {len(paper.get('figures', []))}")
    print(f"  Tables      : {len(paper.get('tables', []))}")
    print(f"  Equations   : {len(paper.get('equations', []))}")
    refs = paper.get("references", [])
    print(f"  References  : {len(refs)}")
    print(f"\n  Token usage : prompt={usage.prompt_tokens}, "
          f"completion={usage.completion_tokens}, total={usage.total_tokens}")
    print(f"\n  Full JSON (first 500 chars of title+abstract+first section):")
    preview = {
        "title": paper.get("title"),
        "abstract": (paper.get("abstract", ""))[:200],
        "first_section": sections[0] if sections else {},
    }
    print(f"  {json.dumps(preview, indent=2)[:500]}")
    print(f"\n[SUCCESS] Paper generated in {elapsed}s")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Independent test for Generate Full Paper with AI"
    )
    parser.add_argument(
        "topic",
        nargs="?",
        default="Lane Detection Algorithm Based on Deep Learning and Computer Vision",
        help="Paper topic (default: lane detection)",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:5000",
        help="Backend server URL (default: http://localhost:5000)",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Call OpenAI directly without a backend server",
    )
    args = parser.parse_args()

    if args.direct:
        success = test_direct_openai(args.topic)
    else:
        success = test_via_server(args.url, args.topic)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
