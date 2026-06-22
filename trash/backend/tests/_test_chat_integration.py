#!/usr/bin/env python3
"""Quick integration test for chat streaming endpoint."""
import json
import sys
import os
import time

import httpx

BASE = "http://localhost:8001"

def test_chat():
    errors = []
    
    # 1. Login
    print("=== STEP 1: Login ===")
    r = httpx.post(f"{BASE}/api/auth/login", json={
        "email": "testbot@test.local",
        "password": "TestBot123!"
    }, timeout=10)
    if r.status_code != 200:
        print(f"  FAIL: login status={r.status_code}, body={r.text[:200]}")
        return
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print(f"  OK: token={token[:20]}...")
    
    # 2. List papers
    print("\n=== STEP 2: List papers ===")
    r = httpx.get(f"{BASE}/api/chat/papers", headers=headers, timeout=10)
    print(f"  Status: {r.status_code}")
    if r.status_code != 200:
        print(f"  FAIL: {r.text[:200]}")
        errors.append(f"list_papers: {r.status_code}")
    else:
        papers = r.json()
        print(f"  Papers count: {len(papers) if isinstance(papers, list) else 'N/A'}")
    
    # 3. Create a paper first
    print("\n=== STEP 3: Create paper ===")
    r = httpx.post(f"{BASE}/api/papers", headers=headers, timeout=10, json={
        "title": "Test Chat Paper",
        "style": "IEEE",
        "language": "en"
    })
    print(f"  Status: {r.status_code}")
    paper_id = None
    if r.status_code in (200, 201):
        paper_id = r.json().get("id") or r.json().get("paper_id")
        print(f"  Paper ID: {paper_id}")
    else:
        print(f"  Body: {r.text[:200]}")
        errors.append(f"create_paper: {r.status_code}")
    
    # 4. Create conversation
    print("\n=== STEP 4: Create conversation ===")
    conv_id = None
    if paper_id:
        r = httpx.post(f"{BASE}/api/papers/{paper_id}/conversations", headers=headers, timeout=10, json={})
        print(f"  Status: {r.status_code}")
        if r.status_code in (200, 201):
            data = r.json()
            conv_id = data.get("id") or data.get("conversation_id")
            print(f"  Conversation ID: {conv_id}")
        else:
            print(f"  Body: {r.text[:200]}")
            errors.append(f"create_conv: {r.status_code}")
    
    # 4. Test sending a message (if we got a conv_id)
    if conv_id:
        print(f"\n=== STEP 4: Send message (SSE) to conv {conv_id} ===")
        try:
            with httpx.stream("POST", 
                f"{BASE}/api/chat/conversations/{conv_id}/messages",
                headers=headers,
                json={"content": "Hello, this is a test message. Respond briefly."},
                timeout=30
            ) as r:
                print(f"  Status: {r.status_code}")
                if r.status_code == 200:
                    events = []
                    for line in r.iter_lines():
                        if line:
                            events.append(line)
                            if len(events) > 20:
                                break
                    print(f"  Events received: {len(events)}")
                    for e in events[:5]:
                        print(f"    {e[:100]}")
                else:
                    body = r.read().decode()
                    print(f"  FAIL: {body[:200]}")
                    errors.append(f"send_message: {r.status_code}")
        except Exception as e:
            print(f"  ERROR: {e}")
            errors.append(f"send_message: {e}")
    
    # 5. Test stream-status endpoint
    if conv_id:
        print(f"\n=== STEP 5: Stream status poll ===")
        r = httpx.get(f"{BASE}/api/chat/conversations/{conv_id}/stream-status", headers=headers, timeout=10)
        print(f"  Status: {r.status_code}, body: {r.text[:200]}")
    
    # 6. Check Redis connectivity
    print("\n=== STEP 6: Redis check ===")
    try:
        import redis
        r = redis.Redis.from_url("redis://localhost:6379/0")
        r.ping()
        keys = r.keys("chat:stream:*")
        print(f"  OK: Redis alive, {len(keys)} active stream keys")
    except Exception as e:
        print(f"  FAIL: {e}")
        errors.append(f"redis: {e}")
    
    print(f"\n{'='*50}")
    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
    else:
        print("ALL TESTS PASSED")

if __name__ == "__main__":
    test_chat()
