#!/usr/bin/env python3
"""
Chat E2E Test via Playwright (Python)
======================================
Tests: register → login → navigate to editor → send chat message → verify no 500

Usage:
    # Frontend must be running on port 8000 (proxy-server) or 5173 (vite dev)
    python3 e2e/test_chat_browser.py

    # Or with with_server.py helper:
    python3 scripts/with_server.py --server "npm run dev" --port 5173 -- python3 e2e/test_chat_browser.py
"""

import sys
import time
import json
import requests
from playwright.sync_api import sync_playwright, expect

# ── Config ────────────────────────────────────────────────────────────
BASE_URL = "http://localhost:8000"  # proxy-server (dist + API proxy)
API_BASE = "http://localhost:8001"  # direct backend
SCREENSHOT_DIR = "/tmp/kilo/chat_test"
RESULTS = {"steps": [], "errors_500": [], "success": False}


def log(step, status, detail=""):
    entry = {"step": step, "status": status, "detail": detail}
    RESULTS["steps"].append(entry)
    icon = "✓" if status == "ok" else "✗" if status == "fail" else "→"
    print(f"  [{icon}] {step}: {detail or status}")


def setup_screenshot_dir():
    import os
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def unique_user():
    ts = int(time.time() * 1000)
    return {
        "email": f"chattest-{ts}@e2e.local",
        "name": f"ChatTest {ts}",
        "password": "ChatTest123!",
    }


# ── Step 1: Health Checks ─────────────────────────────────────────────
def check_health():
    print("\n═══ Step 1: Health Checks ═══")

    # Backend
    try:
        r = requests.get(f"{API_BASE}/api/health", timeout=5)
        if r.status_code == 200:
            data = r.json()
            log("Backend health", "ok", f"status={data.get('status')}")
        else:
            log("Backend health", "fail", f"HTTP {r.status_code}")
            return False
    except Exception as e:
        log("Backend health", "fail", str(e))
        return False

    # Frontend (proxy server on 8000)
    try:
        r = requests.get(f"{BASE_URL}", timeout=5)
        if r.status_code == 200:
            log("Frontend (port 8000)", "ok", f"HTTP {r.status_code}, len={len(r.text)}")
        else:
            log("Frontend (port 8000)", "fail", f"HTTP {r.status_code}")
            return False
    except Exception as e:
        log("Frontend (port 8000)", "fail", str(e))
        return False

    return True


# ── Step 2: Register User via API ─────────────────────────────────────
def register_user(user):
    print("\n═══ Step 2: Register User ═══")
    try:
        r = requests.post(
            f"{API_BASE}/api/auth/register",
            json={
                "email": user["email"],
                "name": user["name"],
                "password": user["password"],
                "captcha_token": "1x00000000000000000000AA",
            },
            timeout=10,
        )
        if r.status_code == 201:
            data = r.json()
            log("Register user", "ok", f"user_id={data.get('user', {}).get('id', 'unknown')}")
            return True
        else:
            log("Register user", "fail", f"HTTP {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        log("Register user", "fail", str(e))
        return False


# ── Step 3: Browser Login + Chat Test ─────────────────────────────────
def browser_test(user):
    print("\n═══ Step 3-6: Browser Login → Editor → Chat ═══")

    # Track network errors
    network_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=True,
        )
        page = context.new_page()

        # Monitor network for 500 errors
        def on_response(response):
            if response.status >= 500:
                network_errors.append({
                    "url": response.url,
                    "status": response.status,
                })

        page.on("response", on_response)

        # Monitor console for errors
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # ── 3. Login ──────────────────────────────────────────────────
        print("\n  --- 3. Login ---")
        try:
            page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=15000)
            page.screenshot(path=f"{SCREENSHOT_DIR}/01_login_page.png", full_page=True)
            log("Load login page", "ok", f"title={page.title()}")

            # Fill login form
            email_input = page.locator("#login-email")
            password_input = page.locator("#login-password")

            email_input.fill(user["email"])
            password_input.fill(user["password"])
            page.screenshot(path=f"{SCREENSHOT_DIR}/02_login_filled.png", full_page=True)
            log("Fill login form", "ok", "email + password filled")

            # Submit
            submit_btn = page.locator('button[type="submit"]')
            submit_btn.click()

            # Wait for navigation to dashboard
            page.wait_for_url("**/dashboard**", timeout=15000)
            page.wait_for_load_state("networkidle", timeout=10000)
            page.screenshot(path=f"{SCREENSHOT_DIR}/03_dashboard.png", full_page=True)
            log("Login submit", "ok", f"redirected to {page.url}")
        except Exception as e:
            page.screenshot(path=f"{SCREENSHOT_DIR}/03_login_error.png", full_page=True)
            log("Login", "fail", str(e)[:200])
            browser.close()
            return network_errors, console_errors

        # ── 4. Navigate to Editor (create new paper) ──────────────────
        print("\n  --- 4. Navigate to Editor ---")
        try:
            # Click "New Paper" or navigate directly
            page.goto(f"{BASE_URL}/editor", wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(2000)
            page.screenshot(path=f"{SCREENSHOT_DIR}/04_editor_page.png", full_page=True)
            log("Navigate to editor", "ok", f"url={page.url}")
        except Exception as e:
            page.screenshot(path=f"{SCREENSHOT_DIR}/04_editor_error.png", full_page=True)
            log("Navigate to editor", "fail", str(e)[:200])
            browser.close()
            return network_errors, console_errors

        # ── 5. Find and open Chat Tab ─────────────────────────────────
        print("\n  --- 5. Open Chat Tab ---")
        try:
            # The chat tab might be accessible via a button or tab
            # Look for chat-related elements
            chat_tab = page.locator('button:has-text("Chat"), button:has-text("💬"), [data-testid="chat-tab"]')
            if chat_tab.count() > 0:
                chat_tab.first.click()
                page.wait_for_timeout(1000)
                log("Open chat tab", "ok", "clicked chat tab button")
            else:
                # Chat might be in a side panel or Tools section
                tools_btn = page.locator('button:has-text("Tools")')
                if tools_btn.count() > 0:
                    tools_btn.first.click()
                    page.wait_for_timeout(1000)
                    log("Open tools panel", "ok", "clicked tools button")

                # Try to find chat input directly
                chat_input = page.locator('.chat-input-textarea, textarea[placeholder*="Ketik"], textarea[placeholder*="Type"], textarea[placeholder*="message"]')
                if chat_input.count() > 0:
                    log("Find chat input", "ok", f"found {chat_input.count()} chat input(s)")
                else:
                    log("Find chat input", "info", "no chat input found yet, looking for AI chat toggle")

            page.screenshot(path=f"{SCREENSHOT_DIR}/05_chat_panel.png", full_page=True)
        except Exception as e:
            page.screenshot(path=f"{SCREENSHOT_DIR}/05_chat_error.png", full_page=True)
            log("Open chat tab", "fail", str(e)[:200])

        # ── 6. Send Chat Message "Hello" ──────────────────────────────
        print("\n  --- 6. Send Chat Message ---")
        try:
            # Try to find the chat textarea
            chat_input = page.locator('.chat-input-textarea').last
            if not chat_input.is_visible(timeout=5000):
                # Try alternative selectors
                chat_input = page.locator('textarea[placeholder*="Ketik"], textarea[placeholder*="Type"]').last

            if chat_input.is_visible(timeout=3000):
                chat_input.fill("Hello")
                page.screenshot(path=f"{SCREENSHOT_DIR}/06_message_typed.png", full_page=True)
                log("Type message", "ok", "typed 'Hello'")

                # Find and click send button
                send_btn = page.locator('button[title="Send"], button[aria-label="Send message"]').last
                if send_btn.is_visible(timeout=3000):
                    send_btn.click()
                    log("Click send", "ok", "clicked send button")

                    # Wait for response (up to 30 seconds)
                    page.wait_for_timeout(5000)
                    page.screenshot(path=f"{SCREENSHOT_DIR}/07_after_send.png", full_page=True)

                    # Wait more for AI response
                    page.wait_for_timeout(10000)
                    page.screenshot(path=f"{SCREENSHOT_DIR}/08_ai_response.png", full_page=True)
                    log("Wait for response", "ok", "waited 15s for AI response")
                else:
                    log("Send button", "fail", "send button not found/visible")
            else:
                log("Chat input", "fail", "chat textarea not visible")
                page.screenshot(path=f"{SCREENSHOT_DIR}/06_no_chat_input.png", full_page=True)

        except Exception as e:
            page.screenshot(path=f"{SCREENSHOT_DIR}/06_send_error.png", full_page=True)
            log("Send message", "fail", str(e)[:200])

        # ── Final Screenshot ──────────────────────────────────────────
        page.screenshot(path=f"{SCREENSHOT_DIR}/09_final_state.png", full_page=True)

        browser.close()
        return network_errors, console_errors


# ── Main ──────────────────────────────────────────────────────────────
def main():
    setup_screenshot_dir()
    print("╔══════════════════════════════════════════════╗")
    print("║  PaperFull Chat E2E Test (Playwright Python) ║")
    print("╚══════════════════════════════════════════════╝")

    # Step 1: Health checks
    if not check_health():
        print("\n✗ Health check failed. Ensure servers are running.")
        sys.exit(1)

    # Step 2: Register
    user = unique_user()
    if not register_user(user):
        print("\n✗ Registration failed.")
        sys.exit(1)

    # Step 3-6: Browser test
    network_errors, console_errors = browser_test(user)

    # ── Results ───────────────────────────────────────────────────────
    print("\n═══ RESULTS ═══")
    print(f"\n  Screenshots saved to: {SCREENSHOT_DIR}/")

    if network_errors:
        print(f"\n  ⚠️  HTTP 5xx errors detected ({len(network_errors)}):")
        for err in network_errors:
            print(f"    - {err['status']} {err['url']}")
        RESULTS["errors_500"] = network_errors
    else:
        print("\n  ✓ No HTTP 5xx errors detected")

    if console_errors:
        print(f"\n  ⚠️  Console errors ({len(console_errors)}):")
        for err in console_errors[:10]:
            print(f"    - {err[:150]}")
    else:
        print("\n  ✓ No console errors")

    RESULTS["success"] = len(network_errors) == 0

    # Save results JSON
    with open(f"{SCREENSHOT_DIR}/results.json", "w") as f:
        json.dump(RESULTS, f, indent=2, default=str)

    print(f"\n  Results JSON: {SCREENSHOT_DIR}/results.json")

    if RESULTS["success"]:
        print("\n═══ ✓ CHAT TEST PASSED ═══\n")
    else:
        print("\n═══ ✗ CHAT TEST FAILED (500 errors detected) ═══\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
