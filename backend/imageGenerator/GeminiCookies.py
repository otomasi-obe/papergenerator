"""Login Google account untuk Gemini lalu scrape cookies-nya untuk dipakai
backend (round-robin 4 akun) di CreateImageGemini.py.

Cara kerja
- Buka Chrome via Playwright (channel=chrome) dengan persistent user-data-dir
  per akun di folder ini. Profile-nya MIRIP MCP Playwright (no-sandbox,
  disable-blink-features=AutomationControlled, viewport 1536x864, dst), jadi
  kalau Google sudah trust IP/UA-nya untuk MCP, login tetap mulus di sini.
- Setelah login terdeteksi, cookies disimpan ke
    imageGenerator/cookies-account{N}.json
  beserta email yang aktif.
- File `.env` di-update otomatis (`GEMINI_ACCOUNT{N}_EMAIL`,
  `GEMINI_ACCOUNT{N}_COOKIES`, `GEMINI_PROFILES_DIR`).

Pemakaian
    python GeminiCookies.py                # login semua slot kosong (1..4) urut
    python GeminiCookies.py --slot 2       # paksa hanya akun #2
    python GeminiCookies.py --refresh      # ulang semua slot meski sudah ada
    python GeminiCookies.py --headless     # jangan dipakai untuk login pertama
    python GeminiCookies.py --check        # cuma verifikasi cookies yang sudah ada

Catatan
- Jangan jalankan barengan dengan MCP Playwright yang memakai user-data-dir
  yang sama (Chrome akan menolak profile dipakai 2x).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


REPO_DIR = Path(__file__).resolve().parent
BACKEND_DIR = REPO_DIR.parent
ENV_PATH = BACKEND_DIR / ".env"

GEMINI_URL = "https://gemini.google.com/app"
ACCOUNTS_URL = "https://myaccount.google.com/"

NUM_SLOTS = 4
DEFAULT_VIEWPORT = (1536, 864)


def _profile_dir(slot: int) -> Path:
    return REPO_DIR / f"account{slot}"


def _cookies_path(slot: int) -> Path:
    return REPO_DIR / f"cookies-account{slot}.json"


def _read_env() -> list[str]:
    if not ENV_PATH.exists():
        return []
    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def _write_env(lines: list[str]) -> None:
    backup = ENV_PATH.with_suffix(".env.bak.geminicookies")
    if ENV_PATH.exists():
        backup.write_text(ENV_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    ENV_PATH.write_text(text, encoding="utf-8")


def _set_env_var(lines: list[str], key: str, value: str) -> list[str]:
    pattern = re.compile(rf"^{re.escape(key)}\s*=")
    out = []
    replaced = False
    for line in lines:
        if pattern.match(line):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    return out


def _update_env(updates: dict[str, str]) -> None:
    lines = _read_env()
    for k, v in updates.items():
        lines = _set_env_var(lines, k, v)
    _write_env(lines)


def _has_required_cookies(context) -> bool:
    try:
        cookies = context.cookies()
    except Exception:
        return False
    have = {
        c.get("name")
        for c in cookies
        if c.get("name") and (c.get("domain") or "").endswith(".google.com")
    }
    return all(n in have for n in _REQUIRED_GEMINI_COOKIES)


def _wait_for_required_cookies(page, *, timeout_s: int = 60) -> bool:
    """Setelah PSID muncul, PSIDTS biasanya menyusul beberapa detik kemudian.
    Tunggu sampai keduanya ter-set, atau timeout."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _has_required_cookies(page.context):
            return True
        try:
            page.reload(wait_until="domcontentloaded", timeout=10_000)
        except Exception:
            pass
        page.wait_for_timeout(2000)
    return _has_required_cookies(page.context)


def _is_logged_in(page) -> tuple[bool, str | None]:
    # Sumber kebenaran: cookie __Secure-1PSID + __Secure-1PSIDTS sudah ter-set
    # di context. Tanpa keduanya, request HTTP ke gemini akan tetap kena redirect
    # login, jadi tidak ada gunanya menganggap "sudah login".
    try:
        ctx = page.context
    except Exception:
        return False, None
    if not _has_required_cookies(ctx):
        return False, None

    try:
        url = page.url or ""
    except Exception:
        url = ""
    if "gemini.google.com" not in url:
        return False, None

    try:
        for pat in (r"Akun Google", r"Google Account"):
            loc = page.get_by_role("button", name=re.compile(pat, re.IGNORECASE))
            if loc.count() > 0:
                label = loc.first.get_attribute("aria-label") or ""
                if not label:
                    try:
                        label = loc.first.inner_text(timeout=500) or ""
                    except Exception:
                        label = ""
                return True, label.strip() or None
    except Exception:
        pass

    try:
        composer = page.get_by_role(
            "textbox",
            name=re.compile(
                r"Masukkan perintah|Minta Gemini|Ask Gemini|Type a prompt|Enter a prompt",
                re.IGNORECASE,
            ),
        )
        if composer.count() > 0:
            return True, None
    except Exception:
        pass

    return False, None


def _wait_for_login(page, *, timeout_s: int) -> tuple[bool, str | None]:
    deadline = time.monotonic() + timeout_s
    next_log = 0.0
    while time.monotonic() < deadline:
        for cand in list(page.context.pages):
            try:
                ok, label = _is_logged_in(cand)
            except PlaywrightError:
                continue
            if ok:
                return True, label
        now = time.monotonic()
        if now >= next_log:
            remaining = int(deadline - now)
            print(f"  ! menunggu login Google ({remaining}s tersisa)…", flush=True)
            next_log = now + 15
        time.sleep(1.0)
    return False, None


def _grab_email(page) -> str | None:
    # Tidak buka myaccount.google.com supaya tidak ganggu Google.
    # Email biasanya muncul di aria-label tombol akun di Gemini, contoh:
    #   "Akun Google: Nama (rofiqcp@gmail.com)"
    try:
        for pat in (r"Akun Google", r"Google Account"):
            loc = page.get_by_role("button", name=re.compile(pat, re.IGNORECASE))
            if loc.count() == 0:
                continue
            label = loc.first.get_attribute("aria-label") or ""
            if not label:
                try:
                    label = loc.first.inner_text(timeout=500) or ""
                except Exception:
                    label = ""
            m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", label)
            if m:
                return m.group(0)
    except Exception:
        pass
    return None


_REQUIRED_GEMINI_COOKIES = ("__Secure-1PSID", "__Secure-1PSIDTS")


def _save_cookies(context, slot: int) -> dict:
    cookies = context.cookies()
    out_path = _cookies_path(slot)
    out_path.write_text(
        json.dumps(cookies, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    have = {
        c["name"]
        for c in cookies
        if c.get("name") and (c.get("domain") or "").endswith(".google.com")
    }
    missing = [n for n in _REQUIRED_GEMINI_COOKIES if n not in have]
    return {
        "path": str(out_path),
        "count": len(cookies),
        "missing": missing,
    }


def _build_context_kwargs(slot: int) -> dict:
    user_data_dir = _profile_dir(slot)
    user_data_dir.mkdir(parents=True, exist_ok=True)

    launch_args = [
        "--profile-directory=Default",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-sandbox",
        "--disable-blink-features=AutomationControlled",
        "--lang=en-US,en",
    ]
    return dict(
        user_data_dir=str(user_data_dir),
        channel="chrome",
        headless=False,
        accept_downloads=True,
        viewport={"width": DEFAULT_VIEWPORT[0], "height": DEFAULT_VIEWPORT[1]},
        args=launch_args,
        ignore_default_args=["--enable-automation"],
        timezone_id="Asia/Bangkok",
    )


def _login_one_slot(p, slot: int, *, headless: bool, timeout_s: int) -> dict:
    print(f"\n=== Slot {slot}: profile {_profile_dir(slot)} ===", flush=True)
    ctx_kwargs = _build_context_kwargs(slot)
    if headless:
        ctx_kwargs["headless"] = True

    context = p.chromium.launch_persistent_context(**ctx_kwargs)
    try:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(GEMINI_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        ok, label = _is_logged_in(page)
        if not ok:
            if headless:
                raise RuntimeError("belum login dan mode headless – jalankan tanpa --headless dulu")
            print(f"  ! belum login. Login Google di window Chrome (timeout {timeout_s}s)…", flush=True)
            ok, label = _wait_for_login(page, timeout_s=timeout_s)
            if not ok:
                raise RuntimeError("login tidak terdeteksi (timeout)")

        # PSIDTS sering nyusul beberapa detik setelah PSID. Tunggu sampai
        # benar2 lengkap supaya cookies file langsung pakai-an oleh CreateImageGemini.py.
        if not _wait_for_required_cookies(page, timeout_s=90):
            print("  ! WARNING: PSIDTS belum muncul setelah 90s; cookies tetap disimpan tapi mungkin perlu refresh ulang.", flush=True)

        email = _grab_email(page) or ""
        info = _save_cookies(context, slot)

        print(f"  ✓ login: {email or label or 'tidak ketahuan'}", flush=True)
        print(f"  ✓ cookies disimpan: {info['path']} ({info['count']} cookie)", flush=True)
        if info["missing"]:
            print(f"  ! WARNING: cookie penting belum lengkap: {info['missing']}", flush=True)
        return {"slot": slot, "email": email, "label": label, **info}
    finally:
        try:
            context.close()
        except Exception:
            pass


def _verify_one_slot(slot: int) -> dict:
    cookies_path = _cookies_path(slot)
    if not cookies_path.exists():
        return {"slot": slot, "ok": False, "reason": "cookies file belum ada"}
    try:
        cookies = json.loads(cookies_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"slot": slot, "ok": False, "reason": f"cookies file rusak: {e}"}
    have = {
        c.get("name")
        for c in cookies
        if c.get("name") and (c.get("domain") or "").endswith(".google.com")
    }
    missing = [n for n in _REQUIRED_GEMINI_COOKIES if n not in have]
    return {
        "slot": slot,
        "ok": not missing,
        "reason": "ok" if not missing else f"cookie kurang: {missing}",
        "count": len(cookies),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", type=int, default=None, help="Hanya proses slot tertentu (1..4)")
    parser.add_argument("--refresh", action="store_true", help="Ulangi login meski cookies sudah ada")
    parser.add_argument("--headless", action="store_true", help="Jangan tampilkan window (hanya berhasil kalau profile sudah login)")
    parser.add_argument("--check", action="store_true", help="Hanya cek cookies yang ada")
    parser.add_argument("--login-timeout", type=int, default=600, help="Detik menunggu login per slot (default 600)")
    args = parser.parse_args()

    slots = [args.slot] if args.slot else list(range(1, NUM_SLOTS + 1))
    for s in slots:
        if not 1 <= s <= NUM_SLOTS:
            raise SystemExit(f"slot harus 1..{NUM_SLOTS}, dapat {s}")

    if args.check:
        all_ok = True
        for s in slots:
            v = _verify_one_slot(s)
            mark = "✓" if v["ok"] else "✗"
            extra = f" ({v.get('count', 0)} cookie)" if v["ok"] else f" – {v['reason']}"
            print(f"{mark} slot {s}{extra}")
            all_ok = all_ok and v["ok"]
        return 0 if all_ok else 1

    env_updates: dict[str, str] = {
        "GEMINI_PROFILES_DIR": str(REPO_DIR),
        "GEMINI_PROFILES": ",".join(f"account{i}" for i in range(1, NUM_SLOTS + 1)),
    }

    results: list[dict] = []
    with sync_playwright() as p:
        for s in slots:
            cookies_path = _cookies_path(s)
            if cookies_path.exists() and not args.refresh:
                v = _verify_one_slot(s)
                if v["ok"]:
                    print(f"slot {s}: cookies sudah ada & valid – skip (pakai --refresh untuk ulang)")
                    results.append({"slot": s, "skipped": True, "path": str(cookies_path)})
                    continue
                print(f"slot {s}: cookies ada tapi tidak valid ({v['reason']}) → re-login")

            try:
                info = _login_one_slot(p, s, headless=args.headless, timeout_s=args.login_timeout)
                results.append(info)
            except Exception as e:
                print(f"  ✗ slot {s} gagal: {e}", flush=True)
                results.append({"slot": s, "error": str(e)})

    for r in results:
        s = r["slot"]
        if r.get("error"):
            continue
        env_updates[f"GEMINI_ACCOUNT{s}_COOKIES"] = str(_cookies_path(s))
        if r.get("email"):
            env_updates[f"GEMINI_ACCOUNT{s}_EMAIL"] = r["email"]

    if env_updates:
        _update_env(env_updates)
        print(f"\n.env diperbarui: {ENV_PATH}")
        for k, v in env_updates.items():
            shown = v if "COOKIES" not in k else v
            print(f"  {k}={shown}")

    failed = [r for r in results if r.get("error")]
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
