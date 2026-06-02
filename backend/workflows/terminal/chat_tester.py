#!/usr/bin/env python3
"""
Terminal Chat Tester — Paper Builder Workflow
=============================================
Tests the AI chat system locally against the workflow spec in
Goal/arsitektur2.md and the conversation examples in Goal/ContohQuestion2/.

Usage:
    python chat_tester.py                    # interactive mode
    python chat_tester.py --auto scenario1  # run a canned scenario
    python chat_tester.py --auto all        # run all canned scenarios
    python chat_tester.py --check-engine    # validate engine phases only (no AI)
    python chat_tester.py --bench           # benchmark: send all ContohQuestion2 msgs

Options:
    --auto <scenario|all>   Run non-interactive scenarios
    --check-engine          Validate workflow engine phases/options (no AI call)
    --bench                 Run all ContohQuestion2 example scenarios and score
    --paper-id <id>         Reuse an existing paper (skips paper creation)
    --user-id  <id>         User ID to run as (default: read from .env)
    --verbose               Print raw API payloads
    --no-color              Disable ANSI colors
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import textwrap
from pathlib import Path
from typing import Any

# ── path setup so we can import backend modules ──────────────────────────
BACKEND = Path(__file__).resolve().parents[2]  # .../backend/
sys.path.insert(0, str(BACKEND))

try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND.parent / ".env")
except ImportError:
    pass

import requests

# ── constants ─────────────────────────────────────────────────────────────
API_BASE     = os.getenv("AIOTOMASI_API", "http://localhost:20128/v1").rstrip("/")
API_KEY      = os.getenv("AIOTOMASI_APIKEY", "")
CHAT_MODEL   = os.getenv("MODELCHAT", "VIOLA-CHAT")
BACKEND_URL  = f"http://localhost:{os.getenv('FLASK_PORT', '8001')}"

GOAL_DIR     = BACKEND.parents[1] / "Goal"
EXAMPLES_DIR = GOAL_DIR / "ContohQuestion2"

# ── ANSI colours ──────────────────────────────────────────────────────────
USE_COLOR = True

def _c(code: str, text: str) -> str:
    if not USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

def cyan(t):    return _c("36", t)
def green(t):   return _c("32", t)
def yellow(t):  return _c("33", t)
def red(t):     return _c("31", t)
def bold(t):    return _c("1", t)
def dim(t):     return _c("2", t)
def magenta(t): return _c("35", t)

# ── import backend modules directly ───────────────────────────────────────
def _load_backend():
    """Load workflow engine + prompts without starting Flask."""
    from workflows.engine import WORKFLOW_PHASES, get_phase_questions, get_next_phase, validate_workflow
    from workflows.tool  import start_workflow, save_workflow_answers
    from chat.mode_prompts import DISCOVERY_PROMPT, get_mode_bundle
    from chat.tools import CHAT_TOOLS, PROPOSAL_PREFIX
    return dict(
        WORKFLOW_PHASES=WORKFLOW_PHASES,
        get_phase_questions=get_phase_questions,
        get_next_phase=get_next_phase,
        validate_workflow=validate_workflow,
        start_workflow=start_workflow,
        save_workflow_answers=save_workflow_answers,
        DISCOVERY_PROMPT=DISCOVERY_PROMPT,
        get_mode_bundle=get_mode_bundle,
        CHAT_TOOLS=CHAT_TOOLS,
        PROPOSAL_PREFIX=PROPOSAL_PREFIX,
    )


# ── AI call (direct, no Flask) ────────────────────────────────────────────
PROPOSAL_RE = re.compile(r"<<PROPOSAL>>\s*(\{.*)", re.DOTALL)

def call_ai(messages: list[dict], tools: list[dict], verbose=False) -> dict:
    """
    Call VIOLA-CHAT directly with the given messages + tools.
    Returns:
        {
          "text":     str,         # assistant text (may be empty)
          "tool_calls": list[dict],  # [{name, arguments}]
          "raw":      dict,        # raw API response body
        }
    """
    url = f"{API_BASE}/chat/completions"
    payload = {
        "model":      CHAT_MODEL,
        "messages":   messages,
        "tools":      tools,
        "stream":     False,
        "max_tokens": 4096,
        "thinking":   {"type": "adaptive"},
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type":  "application/json",
    }

    if verbose:
        print(dim(f"  → POST {url}"))
        print(dim(f"    payload (truncated): {json.dumps(payload, ensure_ascii=False)[:400]}"))

    t0 = time.time()
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    elapsed = time.time() - t0

    if verbose:
        print(dim(f"  ← {resp.status_code} in {elapsed:.1f}s"))

    if resp.status_code != 200:
        return {
            "text": f"[HTTP {resp.status_code}] {resp.text[:300]}",
            "tool_calls": [],
            "raw": {},
            "elapsed": elapsed,
        }

    body = resp.json()
    choice = (body.get("choices") or [{}])[0]
    msg    = choice.get("message", {})

    text       = msg.get("content") or ""
    tool_calls = []
    for tc in (msg.get("tool_calls") or []):
        fn   = tc.get("function", {})
        name = fn.get("name", "")
        try:
            args = json.loads(fn.get("arguments", "{}"))
        except Exception:
            args = {}
        tool_calls.append({"name": name, "arguments": args})

    return {"text": text, "tool_calls": tool_calls, "raw": body, "elapsed": elapsed}


# ── workflow engine checker (no AI) ───────────────────────────────────────
def check_engine(be: dict) -> None:
    """Validate that all workflow phases have well-formed questions."""
    WORKFLOW_PHASES   = be["WORKFLOW_PHASES"]
    get_phase_questions = be["get_phase_questions"]
    get_next_phase    = be["get_next_phase"]

    print(bold("\n=== WORKFLOW ENGINE CHECK ===\n"))
    all_ok = True
    answers_so_far: dict = {}

    phase_order = ["0","1","2","3","4","5","6","7","8","9"]
    for ph in phase_order:
        qs = get_phase_questions(ph, answers_so_far)
        name = WORKFLOW_PHASES.get(ph, {}).get("name", "?")
        print(f"  Phase {ph} — {name}")

        if ph == "9":
            print(f"    {dim('(validation phase — no questions)')}")
            continue

        if not qs:
            print(red(f"    ✗ NO QUESTIONS FOUND"))
            all_ok = False
            continue

        for q in qs:
            qid   = q.get("id", "?")
            label = q.get("label") or q.get("question", "?")
            opts  = q.get("options", [])
            ok    = len(opts) >= 5
            tick  = green("✓") if ok else yellow(f"⚠ only {len(opts)} opts")
            # Check E option exists
            has_E = any(o.get("value") == "E" for o in opts)
            e_mark = green(" [E✓]") if has_E else yellow(" [E missing]")
            print(f"    [{qid}] {label[:55]:<55} {tick}{e_mark}")
            if not ok:
                all_ok = False

        nxt = get_next_phase(ph, answers_so_far)
        print(f"    → next phase: {nxt}")

    print()
    if all_ok:
        print(green("✓ All engine checks passed"))
    else:
        print(yellow("⚠ Some checks failed (see above)"))


# ── proposal decoder ──────────────────────────────────────────────────────
def decode_proposal(text: str) -> dict | None:
    """Extract <<PROPOSAL>>{...} JSON from a string, if present."""
    m = PROPOSAL_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def format_proposal(p: dict) -> str:
    kind = p.get("kind", "?")
    if kind == "multi_question":
        phase = p.get("phase", "?")
        qs    = p.get("questions", [])
        lines = [bold(f"  ┌── MultiQuestion (Phase {phase}: {p.get('phase_name','')})")]
        for q in qs:
            opts_str = "  ".join(
                f"[{o.get('value','?')}] {o.get('label','')}"
                for o in q.get("options", [])
            )
            lines.append(f"  │  [{q.get('id','?')}] {q.get('label', q.get('key',''))}")
            lines.append(f"  │      {dim(opts_str)}")
        lines.append("  └────")
        return "\n".join(lines)

    if kind in ("workflow_validation", "workflow_complete_generating"):
        val = p.get("validation", {})
        warnings = val.get("warnings", [])
        gen = p.get("generation", {})
        lines = [bold(f"  ┌── {kind}")]
        lines.append(f"  │  valid={val.get('valid',False)}  warnings={len(warnings)}")
        for w in warnings[:3]:
            lines.append(f"  │  ⚠ [{w.get('type','')}] {w.get('message','')}")
        if gen:
            lines.append(f"  │  🚀 generation started  job_id={gen.get('job_id','?')}")
        lines.append("  └────")
        return "\n".join(lines)

    if kind == "paper_progress":
        return bold(f"  🚀 paper_progress  job_id={p.get('job_id','?')}")

    return f"  <<PROPOSAL kind={kind}>> {json.dumps(p, ensure_ascii=False)[:120]}"


# ── score a single AI turn against expected criteria ─────────────────────
class TurnResult:
    def __init__(self, phase: str, user_msg: str):
        self.phase    = phase
        self.user_msg = user_msg
        self.passed:  list[str] = []
        self.failed:  list[str] = []

    @property
    def ok(self):
        return len(self.failed) == 0

    def check(self, name: str, condition: bool):
        if condition:
            self.passed.append(name)
        else:
            self.failed.append(name)

    def summary(self) -> str:
        tick = green("✓") if self.ok else red("✗")
        detail = ""
        if self.failed:
            detail = red(f"  FAILED: {', '.join(self.failed)}")
        return f"  {tick} Phase {self.phase:2s} | {self.user_msg[:40]:<40}{detail}"


# ── single conversation session ───────────────────────────────────────────
class Session:
    """
    Simulates one chat conversation with the AI, calling the upstream
    VIOLA-CHAT model directly (no Flask needed).

    The AI uses StartWorkflow/SaveWorkflowAnswers tools which we execute
    against the real workflow backend engine.
    """

    def __init__(self, be: dict, verbose: bool = False, paper_id=None, user_id=None):
        self.be       = be
        self.verbose  = verbose
        self.paper_id = paper_id or "test-paper-1"
        self.user_id  = user_id or "1"
        self.messages: list[dict] = []
        self.results:  list[TurnResult] = []
        self._wf_state: dict = {"current_phase": "0", "answers": {}}
        self._add_system()

    def _add_system(self):
        disc_prompt = self.be["DISCOVERY_PROMPT"]
        self.messages = [{"role": "system", "content": disc_prompt}]

    def _execute_tool(self, name: str, args: dict) -> str:
        """Execute a tool call using the real backend engine (no DB)."""
        be = self.be

        if name == "StartWorkflow":
            state = self._wf_state
            phase = state.get("current_phase", "0")
            answers = state.get("answers", {})
            qs = be["get_phase_questions"](phase, answers)
            formatted = []
            for q in qs:
                qid   = q.get("id", "")
                label = f"[{qid}] {q['question']}" if qid else q["question"]
                formatted.append({"id": qid, "key": q["key"], "label": label, "options": q.get("options", [])})
            result = {
                "kind": "multi_question",
                "phase": phase,
                "phase_name": be["WORKFLOW_PHASES"].get(phase, {}).get("name", ""),
                "questions": formatted,
                "total_phases": 10,
            }
            return "<<PROPOSAL>>" + json.dumps(result, ensure_ascii=False)

        elif name == "SaveWorkflowAnswers":
            raw_answers = args.get("answers", {})
            if isinstance(raw_answers, list):
                for item in raw_answers:
                    self._wf_state["answers"][item["key"]] = item["value"]
            else:
                self._wf_state["answers"].update(raw_answers)

            current  = self._wf_state.get("current_phase", "0")
            next_ph  = be["get_next_phase"](current, self._wf_state["answers"])

            if next_ph == "9":
                val = be["validate_workflow"](self._wf_state["answers"])
                self._wf_state["current_phase"] = "9"
                # Simulate auto-generate trigger
                gen_payload = {
                    "kind": "paper_progress",
                    "job_id": "terminal-test-job",
                    "prompt": self._wf_state["answers"].get("title", "test paper"),
                }
                result = {
                    "kind": "workflow_complete_generating",
                    "validation": val,
                    "message": "Workflow selesai! Paper sedang di-generate.",
                    "generation": gen_payload,
                }
                return "<<PROPOSAL>>" + json.dumps(result, ensure_ascii=False)

            if next_ph:
                self._wf_state["current_phase"] = next_ph
                answers = self._wf_state["answers"]
                qs = be["get_phase_questions"](next_ph, answers)
                formatted = []
                for q in qs:
                    qid   = q.get("id", "")
                    label = f"[{qid}] {q['question']}" if qid else q["question"]
                    formatted.append({"id": qid, "key": q["key"], "label": label, "options": q.get("options", [])})
                result = {
                    "kind": "multi_question",
                    "phase": next_ph,
                    "phase_name": be["WORKFLOW_PHASES"].get(next_ph, {}).get("name", ""),
                    "questions": formatted,
                    "total_phases": 10,
                }
                return "<<PROPOSAL>>" + json.dumps(result, ensure_ascii=False)

            # Completed all phases without validation (shouldn't happen)
            return json.dumps({"kind": "workflow_complete", "message": "Semua fase selesai."})

        elif name == "AskQuestions":
            qs = args.get("questions", [])
            result = {"kind": "multi_question", "questions": qs}
            return "<<PROPOSAL>>" + json.dumps(result, ensure_ascii=False)

        elif name == "ProposeChips":
            result = {"kind": "chips", **args}
            return "<<PROPOSAL>>" + json.dumps(result, ensure_ascii=False)

        else:
            return json.dumps({"status": "ok", "tool": name, "note": "simulated"})

    def chat(self, user_text: str) -> tuple[str, list[dict]]:
        """
        Send one user message, get back (assistant_text, proposals_list).
        Handles tool-call loops internally.
        """
        self.messages.append({"role": "user", "content": user_text})

        tools = self.be["CHAT_TOOLS"]
        all_proposals: list[dict] = []
        full_text = ""
        iteration = 0
        MAX_ITERS = 6

        while iteration < MAX_ITERS:
            iteration += 1
            result = call_ai(self.messages, tools, verbose=self.verbose)
            text       = result["text"] or ""
            tool_calls = result["tool_calls"]

            if text:
                full_text += text

            if not tool_calls:
                # Pure text response — done
                self.messages.append({"role": "assistant", "content": text or ""})
                break

            # Build assistant message with tool_use blocks
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": []}
            if text:
                assistant_msg["content"].append({"type": "text", "text": text})

            tool_results = []
            for tc in tool_calls:
                name     = tc["name"]
                args     = tc["arguments"]
                call_id  = f"call_{name}_{iteration}"

                assistant_msg["content"].append({
                    "type": "tool_use",
                    "id":   call_id,
                    "name": name,
                    "input": args,
                })

                tool_output = self._execute_tool(name, args)
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": call_id,
                    "content":     tool_output,
                })

                # Decode proposal for display
                proposal = decode_proposal(tool_output)
                if proposal:
                    all_proposals.append(proposal)
                    if self.verbose:
                        print(dim(f"    tool {name} → proposal kind={proposal.get('kind')}"))
                elif self.verbose:
                    print(dim(f"    tool {name} → {tool_output[:120]}"))

            self.messages.append(assistant_msg)
            self.messages.append({"role": "user", "content": tool_results})

            # If the last tool call was workflow_complete_generating, stop looping
            if any(p.get("kind") in ("workflow_complete_generating",) for p in all_proposals):
                break

        return full_text, all_proposals

    # ── scoring helpers ────────────────────────────────────────────────────
    def score_turn(self, phase: str, user_msg: str, text: str, proposals: list[dict]) -> TurnResult:
        r = TurnResult(phase, user_msg)
        has_multi_q = any(p.get("kind") == "multi_question" for p in proposals)
        has_text    = bool(text and text.strip())
        has_confirm = bool(text and ("✅" in text or "tercatat" in text.lower()))

        if phase in ("0","1","2","3","4","5","6","7","8"):
            # Expect multi_question proposal
            r.check("has_multi_question_proposal", has_multi_q)
            # Expect confirmation text
            r.check("has_confirmation_text", has_text)
        elif phase == "0_done":
            # After phase 0 done → transition phrase
            r.check("transition_phrase_fase0", "status awal tercatat" in text.lower() or has_confirm)
        elif phase == "1_done":
            # After phase 1 → ringkasan eksekutif table
            r.check("ringkasan_eksekutif_table", "identitas paper" in text.lower() or "|" in text)
        elif phase == "9":
            # Workflow complete + generation started
            has_complete = any(p.get("kind") in ("workflow_complete_generating","workflow_validation") for p in proposals)
            has_gen      = any(p.get("generation") for p in proposals)
            r.check("workflow_complete_proposal", has_complete)
            r.check("generation_auto_triggered", has_gen)
        return r


# ── canned scenarios ──────────────────────────────────────────────────────
SCENARIOS: dict[str, list[dict]] = {

    "scenario1": {
        "description": "Peneliti sosial pemula dari nol (Contoh 3.md)",
        "turns": [
            {"user": "Halo, saya ingin meneliti tentang pemberdayaan masyarakat untuk skripsi.", "check_phase": "0"},
            {"user": "A - masih ide awal",         "check_phase": "0"},
            {"user": "A - belum ada data",          "check_phase": "0"},
            {"user": "A - individu",                "check_phase": "0_done"},
            {"user": "Ilmu Sosial",                 "check_phase": "1"},
            {"user": "Qualitative Research",        "check_phase": "1"},
            {"user": "Skripsi",                     "check_phase": "1_done"},
        ],
    },

    "scenario2": {
        "description": "Path shorthand (Contoh 8.md) + fase lengkap",
        "turns": [
            {"user": "Halo, saya ingin membuat paper tentang Field Study.", "check_phase": "0"},
            {"user": "Path B",    "check_phase": "0_done"},
            {"user": "Environmental Science", "check_phase": "1"},
            {"user": "Field Study",           "check_phase": "1"},
            {"user": "Master's",              "check_phase": "1_done"},
        ],
    },

    "scenario3": {
        "description": "Paperfull trigger — full 9 phases",
        "turns": [
            {"user": "paperfull", "check_phase": "0"},
            {"user": "A", "check_phase": "0"},
            {"user": "A", "check_phase": "0"},
            {"user": "A", "check_phase": "0_done"},
            {"user": "Ilmu Komputer", "check_phase": "1"},
            {"user": "Research Paper", "check_phase": "1"},
            {"user": "Jurnal Scopus",  "check_phase": "1"},
            {"user": "Machine Learning untuk Deteksi Fraud", "check_phase": "1_done"},
            # Phase 2
            {"user": "Deteksi fraud transaksi e-commerce", "check_phase": "2"},
            {"user": "Akurasi model rendah pada class imbalance", "check_phase": "2"},
            {"user": "Belum ada benchmark khusus UMKM", "check_phase": "2"},
            {"user": "Bagaimana meningkatkan akurasi deteksi fraud?", "check_phase": "2"},
            {"user": "Membandingkan XGBoost vs LSTM vs Random Forest", "check_phase": "2"},
            {"user": "fraud detection, machine learning, imbalanced data", "check_phase": "2"},
            # Phase 3
            {"user": "Kuantitatif", "check_phase": "3"},
            {"user": "XGBoost dengan SMOTE oversampling", "check_phase": "3"},
            {"user": "Kaggle credit card fraud dataset", "check_phase": "3"},
            {"user": "50000 transaksi", "check_phase": "3"},
            {"user": "Python, scikit-learn, pandas", "check_phase": "3"},
            {"user": "Tidak perlu etik", "check_phase": "3"},
            # Phase 4
            {"user": "IEEE template", "check_phase": "4"},
            {"user": "Sedang (Sinta 2-3)", "check_phase": "4"},
            {"user": "5 sections", "check_phase": "4"},
            {"user": "Hasil eksperimen", "check_phase": "4"},
            {"user": "Intro, Related, Method, Result, Conclusion", "check_phase": "4"},
            # Phase 5
            {"user": "IEEE", "check_phase": "5"},
            {"user": "30-40 referensi", "check_phase": "5"},
            {"user": "2019-2024", "check_phase": "5"},
            {"user": "Crossref dan Semantic Scholar", "check_phase": "5"},
            {"user": "Wajib DOI", "check_phase": "5"},
            # Phase 6
            {"user": "Bar chart dan confusion matrix", "check_phase": "6"},
            {"user": "5 gambar", "check_phase": "6"},
            {"user": "Matplotlib", "check_phase": "6"},
            {"user": "Tabel perbandingan model", "check_phase": "6"},
            # Phase 7
            {"user": "Bahasa Inggris", "check_phase": "7"},
            {"user": "Formal akademik", "check_phase": "7"},
            {"user": "Third person passive", "check_phase": "7"},
            {"user": "Orisinalitas", "check_phase": "7"},
            {"user": "20% max AI detection", "check_phase": "7"},
            # Phase 8
            {"user": "Ahmad Suharto", "check_phase": "8"},
            {"user": "Tidak ada konflik kepentingan", "check_phase": "8"},
            {"user": "3 bulan", "check_phase": "8"},
            {"user": "Belum ada reviewer", "check_phase": "8"},
            {"user": "DOCX dan PDF", "check_phase": "8"},
            {"user": "Tidak ada data sensitif", "check_phase": "9"},
        ],
    },
}


# ── run a scenario ─────────────────────────────────────────────────────────
def run_scenario(name: str, scenario: dict, be: dict, verbose=False) -> list[TurnResult]:
    desc  = scenario["description"]
    turns = scenario["turns"]

    print(bold(f"\n{'='*60}"))
    print(bold(f"SCENARIO: {name}"))
    print(f"  {dim(desc)}")
    print(bold(f"{'='*60}"))

    session = Session(be, verbose=verbose)
    results = []

    for i, turn in enumerate(turns):
        user_msg    = turn["user"]
        check_phase = turn.get("check_phase", "?")

        print(f"\n{cyan(f'[Turn {i+1}]')} {bold('User:')} {user_msg}")

        t0   = time.time()
        text, proposals = session.chat(user_msg)
        elapsed = time.time() - t0

        # Print AI response
        if text:
            wrapped = textwrap.fill(text.strip(), width=70, subsequent_indent="  ")
            print(f"{magenta('  AI:')} {wrapped}")

        # Print proposals
        for p in proposals:
            print(format_proposal(p))

        print(dim(f"  ({elapsed:.1f}s)"))

        # Score
        result = session.score_turn(check_phase, user_msg, text, proposals)
        results.append(result)
        print(result.summary())

    return results


# ── benchmark against ContohQuestion2 examples ───────────────────────────
def run_bench(be: dict, verbose=False) -> None:
    """Parse ContohQuestion2/*.md and run each as a session."""
    if not EXAMPLES_DIR.exists():
        print(red(f"ContohQuestion2 directory not found: {EXAMPLES_DIR}"))
        return

    files = sorted(EXAMPLES_DIR.glob("*.md"))
    print(bold(f"\n{'='*60}"))
    print(bold(f"BENCHMARK: {len(files)} ContohQuestion2 scenarios"))
    print(bold(f"{'='*60}"))

    total_pass = 0
    total_fail = 0

    for f in files[:5]:  # cap at 5 for speed; remove slice for full bench
        print(bold(f"\n── {f.name} ──"))
        content = f.read_text(encoding="utf-8")

        # Extract user turns from markdown: lines starting with **User:**
        user_turns = re.findall(r'\*\*User:\*\*\s*(.+?)(?=\n\n|\Z)', content, re.DOTALL)
        if not user_turns:
            print(dim("  (no user turns found)"))
            continue

        session = Session(be, verbose=verbose)
        for turn_text in user_turns[:6]:  # first 6 turns per scenario
            turn_text = turn_text.strip()
            print(f"{cyan('User:')} {turn_text[:80]}")
            text, proposals = session.chat(turn_text)
            if text:
                print(f"{magenta('AI:')} {text[:100].strip()}")
            for p in proposals:
                print(format_proposal(p))

            # Basic checks
            has_q = any(p.get("kind") == "multi_question" for p in proposals)
            has_plain_q = bool(re.search(r'\[OPSI\]|\[A\]|\*\*\[', text or ''))

            if has_plain_q:
                print(red("  ✗ FAIL: AI wrote questions as plain text (should use AskQuestions tool)"))
                total_fail += 1
            elif has_q:
                print(green("  ✓ PASS: questions delivered via tool"))
                total_pass += 1
            elif text:
                print(yellow("  ~ INFO: text only (no questions — may be ok)"))

    print(bold(f"\nBENCHMARK RESULT: {green(str(total_pass))} passed, {red(str(total_fail))} failed"))


# ── interactive mode ──────────────────────────────────────────────────────
def interactive_mode(be: dict, verbose=False) -> None:
    print(bold("\n=== Paper Builder Terminal Chat (interactive) ==="))
    print(dim("Commands: /quit  /reset  /phases  /state  /score\n"))

    session = Session(be, verbose=verbose)
    turn_n  = 0

    while True:
        try:
            line = input(cyan("You: ")).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not line:
            continue

        if line == "/quit":
            break
        elif line == "/reset":
            session = Session(be, verbose=verbose)
            print(yellow("Session reset."))
            continue
        elif line == "/phases":
            check_engine(be)
            continue
        elif line == "/state":
            print(yellow(f"Workflow state: {json.dumps(session._wf_state, indent=2, ensure_ascii=False)}"))
            continue
        elif line == "/score":
            passed = sum(1 for r in session.results if r.ok)
            total  = len(session.results)
            print(yellow(f"Score: {passed}/{total} turns passed"))
            for r in session.results:
                print(r.summary())
            continue

        turn_n += 1
        t0 = time.time()
        text, proposals = session.chat(line)
        elapsed = time.time() - t0

        if text:
            print(f"{magenta('AI:')} {text.strip()}")

        for p in proposals:
            print(format_proposal(p))

        print(dim(f"  ({elapsed:.1f}s)"))


# ── main ──────────────────────────────────────────────────────────────────
def main():
    global USE_COLOR

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--auto",        metavar="SCENARIO", help="Run canned scenario (name or 'all')")
    ap.add_argument("--check-engine",action="store_true", help="Validate workflow engine only")
    ap.add_argument("--bench",       action="store_true", help="Benchmark against ContohQuestion2")
    ap.add_argument("--paper-id",    default=None,       help="Paper ID to use")
    ap.add_argument("--user-id",     default="1",        help="User ID to use")
    ap.add_argument("--verbose",     action="store_true", help="Print raw payloads")
    ap.add_argument("--no-color",    action="store_true", help="Disable colors")
    args = ap.parse_args()

    if args.no_color:
        USE_COLOR = False

    print(bold("Loading backend modules..."), end=" ", flush=True)
    try:
        be = _load_backend()
        print(green("OK"))
    except Exception as e:
        print(red(f"FAILED: {e}"))
        import traceback; traceback.print_exc()
        sys.exit(1)

    print(f"  VIOLA-CHAT: {dim(CHAT_MODEL)} @ {dim(API_BASE)}")
    print(f"  API key:    {dim(API_KEY[:8] + '...' if API_KEY else 'NOT SET')}")

    if args.check_engine:
        check_engine(be)
        return

    if args.bench:
        run_bench(be, verbose=args.verbose)
        return

    if args.auto:
        target = args.auto
        to_run = SCENARIOS if target == "all" else {target: SCENARIOS.get(target)}

        if not any(to_run.values()):
            print(red(f"Unknown scenario '{target}'. Available: {list(SCENARIOS.keys())}"))
            sys.exit(1)

        all_results: list[TurnResult] = []
        for name, scenario in to_run.items():
            if scenario is None:
                continue
            results = run_scenario(name, scenario, be, verbose=args.verbose)
            all_results.extend(results)

        passed = sum(1 for r in all_results if r.ok)
        total  = len(all_results)
        print(bold(f"\n{'='*60}"))
        print(bold(f"TOTAL: {green(str(passed))}/{total} turns passed"))
        if passed < total:
            print(red("FAILED turns:"))
            for r in all_results:
                if not r.ok:
                    print(r.summary())
        return

    # Default: interactive
    interactive_mode(be, verbose=args.verbose)


if __name__ == "__main__":
    main()
