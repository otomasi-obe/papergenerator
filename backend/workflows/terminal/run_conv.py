#!/usr/bin/env python3
"""
Conversation Runner — Paper Builder Workflow Test
=================================================
Menjalankan percakapan U: / AI: sesuai skenario ContohQuestion2,
menyimpan history ke 1.txt … 30.txt.

Usage:
    python run_conv.py           # jalankan semua 30 skenario otomatis
    python run_conv.py 1         # jalankan skenario 1 saja
    python run_conv.py 1 5       # jalankan skenario 1-5
    python run_conv.py --list    # lihat daftar skenario

Output tersimpan di:
    /home/sirobo/papergenerator/backend/workflows/terminal/1.txt … 30.txt
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

# ─── path setup ───────────────────────────────────────────────────────────
BACKEND     = Path(__file__).resolve().parents[2]
TERMINAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND.parent / ".env")
except ImportError:
    pass

import requests

# ─── config ───────────────────────────────────────────────────────────────
API_BASE   = os.getenv("AIOTOMASI_API", "http://localhost:20128/v1").rstrip("/")
API_KEY    = os.getenv("AIOTOMASI_APIKEY", "")
CHAT_MODEL = os.getenv("MODELCHAT", "VIOLA-CHAT")

# ─── ANSI colors ─────────────────────────────────────────────────────────
def cyan(t):    return f"\033[36m{t}\033[0m"
def green(t):   return f"\033[32m{t}\033[0m"
def yellow(t):  return f"\033[33m{t}\033[0m"
def red(t):     return f"\033[31m{t}\033[0m"
def bold(t):    return f"\033[1m{t}\033[0m"
def dim(t):     return f"\033[2m{t}\033[0m"
def magenta(t): return f"\033[35m{t}\033[0m"

# ─── load backend modules (no Flask) ────────────────────────────────────
def _load_be():
    from workflows.engine   import WORKFLOW_PHASES, get_phase_questions, get_next_phase, validate_workflow
    from chat.mode_prompts  import DISCOVERY_PROMPT
    from chat.tools         import CHAT_TOOLS
    return dict(
        WORKFLOW_PHASES     = WORKFLOW_PHASES,
        get_phase_questions = get_phase_questions,
        get_next_phase      = get_next_phase,
        validate_workflow   = validate_workflow,
        DISCOVERY_PROMPT    = DISCOVERY_PROMPT,
        CHAT_TOOLS          = CHAT_TOOLS,
    )


# ─── call AI ─────────────────────────────────────────────────────────────
def call_ai(messages: list, tools: list, max_retries: int = 3) -> dict:
    """Call AI with retry logic and progress indication."""
    url     = f"{API_BASE}/chat/completions"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model":      CHAT_MODEL,
        "messages":   messages,
        "tools":      tools,
        "stream":     False,
        "max_tokens": 4096,
        "thinking":   {"type": "adaptive"},
    }
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                wait = min(2 ** attempt, 10)  # exponential backoff, max 10s
                print(dim(f"    ⟳ Retry {attempt+1}/{max_retries} (tunggu {wait}s...)"))
                time.sleep(wait)
            
            t0 = time.time()
            print(dim(f"    ⏳ Memanggil AI..."), end="", flush=True)
            
            resp = requests.post(url, headers=headers, json=payload, timeout=300)
            elapsed = time.time() - t0
            
            print(f"\r    {dim(f'✓ Respons diterima ({elapsed:.1f}s)')}")
            
            if resp.status_code != 200:
                err_msg = f"[HTTP {resp.status_code}] {resp.text[:200]}"
                if attempt < max_retries - 1:
                    print(yellow(f"    ⚠ {err_msg}"))
                    continue
                return {"text": err_msg, "tool_calls": [], "elapsed": elapsed}

            body   = resp.json()
            choice = (body.get("choices") or [{}])[0]
            msg    = choice.get("message", {})
            text   = msg.get("content") or ""

            tool_calls = []
            for tc in (msg.get("tool_calls") or []):
                fn = tc.get("function", {})
                try:   args = json.loads(fn.get("arguments", "{}"))
                except: args = {}
                tool_calls.append({"name": fn.get("name",""), "arguments": args, "id": tc.get("id","")})

            return {"text": text, "tool_calls": tool_calls, "elapsed": elapsed}
            
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                print(yellow(f"\n    ⚠ Timeout setelah 300s"))
                continue
            return {"text": "[TIMEOUT] AI tidak merespons dalam 300 detik", "tool_calls": [], "elapsed": 300}
            
        except requests.exceptions.ConnectionError as e:
            if attempt < max_retries - 1:
                print(yellow(f"\n    ⚠ Koneksi error: {e}"))
                continue
            return {"text": f"[CONNECTION ERROR] {e}", "tool_calls": [], "elapsed": 0}
            
        except Exception as e:
            if attempt < max_retries - 1:
                print(yellow(f"\n    ⚠ Error: {e}"))
                continue
            return {"text": f"[ERROR] {e}", "tool_calls": [], "elapsed": 0}
    
    return {"text": "[FAILED] Semua retry gagal", "tool_calls": [], "elapsed": 0}


# ─── workflow state (in-memory, no DB) ───────────────────────────────────
class WorkflowState:
    def __init__(self, be: dict):
        self.be      = be
        self.phase   = "0"
        self.answers: dict = {}
        # Snapshot of the options last presented to the user, keyed by question
        # key -> {value: label}. Captures AI-generated options too so A/B/C/D
        # resolve to full text even outside the static WORKFLOW_PHASES.
        self.pending_options: dict = {}

    def _build_multi_q(self, phase: str) -> dict:
        qs = self.be["get_phase_questions"](phase, self.answers)
        formatted = []
        snapshot: dict = {}
        for q in qs:
            qid   = q.get("id", "")
            label = f"[{qid}] {q['question']}" if qid else q["question"]
            opts  = q.get("options", [])
            formatted.append({"id": qid, "key": q["key"], "label": label, "options": opts})
            opt_map = {}
            for o in opts or []:
                val = o.get("value")
                lab = o.get("label")
                if val is not None and lab is not None:
                    opt_map[str(val)] = lab
            if opt_map:
                snapshot[q["key"]] = opt_map
        # Remember exactly what we showed so save_answers can resolve codes.
        self.pending_options = snapshot
        return {
            "kind":        "multi_question",
            "phase":       phase,
            "phase_name":  self.be["WORKFLOW_PHASES"].get(phase, {}).get("name", ""),
            "questions":   formatted,
            "total_phases": 10,
        }

    def start(self) -> str:
        result = self._build_multi_q("0")
        return "<<PROPOSAL>>" + json.dumps(result, ensure_ascii=False)

    def _resolve_answer_text(self, question_key: str, answer_value: str) -> str:
        """Resolve full text from answer value (A/B/C/D -> label text).

        Resolution order: presented-options snapshot → static WORKFLOW_PHASES
        (main + branches) → raw input (custom/free-text answer).
        """
        value_str = answer_value if isinstance(answer_value, str) else str(answer_value)

        # 1) Snapshot of what was actually shown (covers AI-generated options).
        opt_map = self.pending_options.get(question_key)
        if opt_map and value_str in opt_map:
            return opt_map[value_str]

        phase_def = self.be["WORKFLOW_PHASES"].get(self.phase, {})

        # 2) Static main questions.
        for q in phase_def.get("questions", []):
            if q.get("key") == question_key:
                for opt in q.get("options", []):
                    if opt.get("value") == answer_value:
                        return opt.get("label", answer_value)
                return answer_value

        # 2b) Static branches (phase 6).
        for branch_name, branch_def in phase_def.get("branches", {}).items():
            for q in branch_def.get("questions", []):
                if q.get("key") == question_key:
                    for opt in q.get("options", []):
                        if opt.get("value") == answer_value:
                            return opt.get("label", answer_value)
                    return answer_value

        # 3) Custom / free-text answer.
        return answer_value

    def save_answers(self, raw_answers: dict | list) -> str:
        if isinstance(raw_answers, list):
            for item in raw_answers:
                key = item["key"]
                value = item["value"]
                # Resolve to full text
                full_text = self._resolve_answer_text(key, value)
                self.answers[key] = full_text
        else:
            for key, value in raw_answers.items():
                # Resolve to full text
                full_text = self._resolve_answer_text(key, value)
                self.answers[key] = full_text

        next_ph = self.be["get_next_phase"](self.phase, self.answers)

        if next_ph == "9":
            self.phase = "9"
            val = self.be["validate_workflow"](self.answers)
            gen = {"kind": "paper_progress", "job_id": "terminal-sim-job",
                   "prompt": self.answers.get("title", self.answers.get("topic", "paper"))}
            result = {
                "kind":       "workflow_complete_generating",
                "validation": val,
                "message":    "✅ Semua fase selesai! Paper sedang di-generate (simulasi).",
                "generation": gen,
            }
            return "<<PROPOSAL>>" + json.dumps(result, ensure_ascii=False)

        if next_ph:
            self.phase = next_ph
            result = self._build_multi_q(next_ph)
            return "<<PROPOSAL>>" + json.dumps(result, ensure_ascii=False)

        self.phase = "done"
        return json.dumps({"kind": "workflow_complete", "message": "Workflow selesai."})

    def execute(self, name: str, args: dict) -> str:
        if name == "StartWorkflow":
            return self.start()
        if name == "SaveWorkflowAnswers":
            return self.save_answers(args.get("answers", {}))
        if name == "AskQuestions":
            result = {"kind": "multi_question", "questions": args.get("questions", [])}
            return "<<PROPOSAL>>" + json.dumps(result, ensure_ascii=False)
        # Simulate other tools benign-ly
        return json.dumps({"status": "ok", "tool": name})


# ─── proposal → human-readable text ─────────────────────────────────────
def proposal_to_text(p: dict) -> str:
    """Render a <<PROPOSAL>> dict as readable U:/AI: conversation text."""
    kind = p.get("kind", "?")

    if kind == "multi_question":
        phase = p.get("phase", "?")
        pname = p.get("phase_name", "")
        lines = [f"[FASE {phase} — {pname}]"]
        for q in p.get("questions", []):
            lines.append(f"\n{q.get('label', q.get('key',''))}")
            for o in q.get("options", []):
                lines.append(f"  [{o.get('value','?')}] {o.get('label','')}")
        return "\n".join(lines)

    if kind in ("workflow_complete_generating", "workflow_validation"):
        val  = p.get("validation", {})
        warns = val.get("warnings", [])
        gen  = p.get("generation", {})
        lines = [p.get("message", "Workflow selesai!")]
        if warns:
            lines.append(f"\n⚠ {len(warns)} peringatan validasi:")
            for w in warns[:3]:
                lines.append(f"  • [{w.get('type','')}] {w.get('message','')}")
        if gen:
            lines.append(f"\n🚀 Paper generation dimulai (job_id: {gen.get('job_id','?')})")
            lines.append("   Editor akan auto-load hasil dalam 3-10 menit.")
        return "\n".join(lines)

    if kind == "paper_progress":
        return f"🚀 Paper generation dimulai (job_id: {p.get('job_id','?')})\n   Editor akan auto-load hasil dalam 3-10 menit."

    if kind == "chips":
        chips = p.get("chips", [])
        return "Pilihan cepat: " + "  ".join(f"[{c}]" for c in chips)

    return f"[{kind}] " + json.dumps(p, ensure_ascii=False)[:200]


# ─── one full chat session ────────────────────────────────────────────────
class ConvSession:
    def __init__(self, be: dict, scenario_title: str = ""):
        self.be      = be
        self.title   = scenario_title
        self.wf      = WorkflowState(be)
        self.msgs: list[dict] = [{"role": "system", "content": be["DISCOVERY_PROMPT"]}]
        self.log:  list[str]  = []          # lines for .txt file
        
        # Filter tools to only workflow-related ones for faster AI responses
        all_tools = be["CHAT_TOOLS"]
        workflow_tool_names = {"StartWorkflow", "SaveWorkflowAnswers", "AskQuestions"}
        self.tools = [t for t in all_tools if t.get("function", {}).get("name") in workflow_tool_names]

    def _log(self, line: str, print_line: bool = True):
        self.log.append(line)
        if print_line:
            print(line)

    def send(self, user_text: str | list[str]) -> tuple[str, int]:
        """Send user message (string or list of answers), return (AI reply, num_questions_asked)."""
        # Handle list of answers for multi-question responses
        if isinstance(user_text, list):
            display_text = ", ".join(user_text)
            # Format as JSON array for AI to parse
            user_text = json.dumps(user_text, ensure_ascii=False)
        else:
            display_text = user_text
        
        self._log(f"\nU: {display_text}")
        self.msgs.append({"role": "user", "content": user_text})

        full_reply_parts: list[str] = []
        num_questions = 0
        MAX_LOOPS = 6

        for loop in range(MAX_LOOPS):
            # Trim message history to last 10 messages to reduce token count
            msgs_to_send = self.msgs[:1] + self.msgs[-9:] if len(self.msgs) > 10 else self.msgs
            
            result    = call_ai(msgs_to_send, self.tools)
            text      = result["text"] or ""
            tool_calls = result["tool_calls"]
            elapsed   = result["elapsed"]

            if text:
                full_reply_parts.append(text.strip())

            if not tool_calls:
                self.msgs.append({"role": "assistant", "content": text or ""})
                break

            # Build assistant message with tool_use blocks (Anthropic style)
            asst_content: list[dict] = []
            if text:
                asst_content.append({"type": "text", "text": text})

            tool_results: list[dict] = []
            for tc in tool_calls:
                name    = tc["name"]
                args    = tc["arguments"]
                call_id = tc.get("id") or f"call_{name}_{loop}"

                asst_content.append({"type": "tool_use", "id": call_id, "name": name, "input": args})

                output   = self.wf.execute(name, args)
                tool_results.append({"type": "tool_result", "tool_use_id": call_id, "content": output})

                # decode proposals into readable text and count questions
                if "<<PROPOSAL>>" in output:
                    try:
                        p = json.loads(output[output.index("<<PROPOSAL>>") + len("<<PROPOSAL>>"):])
                        full_reply_parts.append(proposal_to_text(p))
                        
                        # Count questions in this proposal
                        if p.get("kind") == "multi_question":
                            num_questions = len(p.get("questions", []))
                    except Exception:
                        pass

                # Stop looping after workflow completes
                if "workflow_complete_generating" in output:
                    self.msgs.append({"role": "assistant", "content": asst_content})
                    self.msgs.append({"role": "user",      "content": tool_results})
                    loop = MAX_LOOPS  # break outer
                    break

            self.msgs.append({"role": "assistant", "content": asst_content})
            self.msgs.append({"role": "user",      "content": tool_results})

            if self.wf.phase == "9":
                break

        ai_reply = "\n".join(filter(None, full_reply_parts))
        self._log(f"\nAI: {ai_reply}")
        self._log(f"    {dim(f'({elapsed:.1f}s)')}")
        return ai_reply, num_questions

    def save(self, path: Path):
        """Write the full conversation log to a .txt file, cleaned of ANSI codes."""
        # Remove ANSI color codes from log
        ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
        cleaned_log = [ansi_escape.sub('', line) for line in self.log]
        
        header = [
            f"# Skenario: {self.title}",
            f"# Tanggal : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# Model   : {CHAT_MODEL}",
            f"# Fase akhir: {self.wf.phase}",
            f"# Jawaban terkumpul: {len(self.wf.answers)}",
            "=" * 60,
        ]
        path.write_text("\n".join(header) + "\n" + "\n".join(cleaned_log), encoding="utf-8")
        print(green(f"  → Disimpan ke {path}"))


# ─── 30 skenario ─────────────────────────────────────────────────────────
# Format: setiap turn bisa berupa:
#   - String tunggal: "A" atau "Judul paper saya..."
#   - List jawaban: ["A", "B", "C"] untuk menjawab multiple questions sekaligus
SCENARIOS: list[dict] = [
    # 1 ─ Sosial pemula dari nol
    {"title": "Sosial Pemula — Skripsi dari Nol",
     "turns": [
         "Halo, saya ingin meneliti tentang pemberdayaan masyarakat untuk skripsi.",
         ["A", "A", "A"],  # [0.1] progress: baru mulai, [0.2] data: belum ada, [0.3] tim: sendiri
         ["A", "A", "A"],  # [1.1] bidang: Sosial, [1.2] jenis: Skripsi, [1.3] target: ujian skripsi
         ["A", "A", "A"],  # [2.1] topik: ekonomi UMKM, [2.2] problem: akses pasar, [2.3] gap: studi wilayah
         ["A", "A", "A"],  # [3.1] metode: kualitatif, [3.2] pengumpulan: wawancara, [3.3] sumber: masyarakat
         ["A", "A", "B"],  # [4.1] struktur: standar kampus, [4.2] kompleksitas: sederhana, [4.3] bagian: 5-7
         ["A", "B", "B"],  # [5.1] sitasi: APA, [5.2] referensi: 16-25, [5.3] tahun: 5 tahun terakhir
         ["A", "B", "A"],  # [6.1] visualisasi: tabel grafik, [6.2] jumlah: 3-4, [6.3] platform: Excel
         "Pemberdayaan Masyarakat Melalui Program UMKM di Desa Binaan",  # judul
         ["A", "B", "B"],  # [7.1] bahasa: Indonesia, [7.2] nada: populer-educative, [7.3] gaya: orang ketiga
         ["A", "B", "A"],  # [8.1] tim penulis: sendiri, [8.2] supplementary: ada, [8.3] biaya: tidak ada
     ]},

    # 2 ─ Teknik intermediate
    {"title": "Teknik Intermediate — Material Komposit Tesis",
     "turns": [
         "Halo, saya sudah punya metode pengujian material komposit, butuh bantuan struktur paper.",
         ["B", "B", "A"],  # progress: ada outline, data: mentah, tim: sendiri
         ["C", "A", "B"],  # bidang: Teknik, jenis: Skripsi, target: jurnal nasional
         ["B", "B", "B"],  # topik: material, problem: kekuatan, gap: metode baru
         ["B", "B", "A"],  # metode: kuantitatif, pengumpulan: kuesioner, sumber: masyarakat
         ["B", "B", "B"],  # struktur: IMRaD, kompleksitas: menengah, bagian: 5-7
         ["A", "B", "B"],  # sitasi: APA, referensi: 16-25, tahun: 5 tahun
         ["A", "B", "A"],  # visualisasi: tabel, jumlah: 3-4, platform: Excel
         "Analisis Kekuatan Tarik Komposit Serat Bambu-Epoxy pada Variasi Fraksi Volume",
         ["A", "A", "B"],  # bahasa: Indonesia, nada: akademis formal, gaya: orang ketiga
         ["A", "A", "B"],  # tim: sendiri, supplementary: tidak, biaya: ada
     ]},

    # 3 ─ Bisnis studi kasus
    {"title": "Bisnis — Case Study Transformasi Digital",
     "turns": [
         "Halo, saya sudah mengumpulkan data studi kasus transformasi digital di perusahaan retail.",
         ["C", "D", "B"],  # progress: draft sebagian, data: final siap, tim: 2-3 orang
         ["A", "A", "B"],  # bidang: Sosial, jenis: Skripsi, target: jurnal nasional
         ["D", "D", "B"],  # topik: digital, problem: kesenjangan digital, gap: metode
         ["C", "B", "B"],  # metode: mixed, pengumpulan: kuesioner, sumber: UMKM
         ["B", "B", "B"],  # struktur: IMRaD, kompleksitas: menengah, bagian: 5-7
         ["A", "B", "B"],  # sitasi: APA, referensi: 16-25, tahun: 5 tahun
         ["A", "B", "B"],  # visualisasi: tabel, jumlah: 3-4, platform: Python
         "Strategi Transformasi Digital dan Dampaknya pada Kinerja Operasional Retail",
         ["A", "B", "B"],  # bahasa: Indonesia, nada: populer, gaya: orang ketiga
         ["B", "A", "A"],  # tim: 2-3 orang, supplementary: ada, biaya: tidak
     ]},

    # 4 ─ Pendidikan action research
    {"title": "Pendidikan — Action Research Matematika SD",
     "turns": [
         "Halo, saya sudah merancang metode pembelajaran inovatif untuk matematika SD.",
         ["B", "B", "A"],  # progress: ada ide, data: pilot study, tim: sendiri
         ["A", "A", "A"],  # bidang: Sosial, jenis: Skripsi, target: ujian
         ["B", "B", "A"],  # topik: pendidikan, problem: kesadaran, gap: studi wilayah
         ["A", "A", "A"],  # metode: kualitatif, pengumpulan: wawancara, sumber: masyarakat
         ["A", "A", "B"],  # struktur: standar, kompleksitas: sederhana, bagian: 5-7
         ["A", "B", "B"],  # sitasi: APA, referensi: 16-25, tahun: 5 tahun
         ["A", "B", "A"],  # visualisasi: tabel, jumlah: 3-4, platform: Excel
         "Penerapan Metode Gamifikasi untuk Meningkatkan Hasil Belajar Matematika Siswa SD Kelas 4",
         ["A", "B", "B"],  # bahasa: Indonesia, nada: populer, gaya: orang ketiga
         ["A", "A", "A"],  # tim: sendiri, supplementary: ada, biaya: tidak
     ]},

    # 5 ─ Psikologi eksperimen
    {"title": "Psikologi Advanced — Working Memory Scopus",
     "turns": [
         "Halo, saya sudah menyelesaikan eksperimen tentang working memory dan attention.",
         ["C", "D", "B"],  # progress: draft, data: final, tim: 2-3
         ["A", "B", "C"],  # bidang: Sosial, jenis: Artikel Jurnal, target: internasional
         ["A", "A", "C"],  # topik: ekonomi, problem: akses pasar, gap: dampak jangka panjang
         ["B", "B", "A"],  # metode: kuantitatif, pengumpulan: kuesioner, sumber: masyarakat
         ["B", "C", "B"],  # struktur: IMRaD, kompleksitas: kompleks, bagian: 5-7
         ["A", "C", "D"],  # sitasi: APA, referensi: 26-35, tahun: campuran
         ["A", "C", "B"],  # visualisasi: tabel, jumlah: 5-6, platform: Python
         "Working Memory Capacity and Attention Allocation in Dual-Task Performance: A Cognitive Load Study",
         ["B", "A", "B"],  # bahasa: Inggris, nada: akademis, gaya: orang ketiga
         ["B", "A", "B"],  # tim: 2-3, supplementary: ada, biaya: ada
     ]},

    # 6 ─ Lingkungan Field Study
    {"title": "Lingkungan — Field Study Master's",
     "turns": [
         "Halo, saya ingin membuat paper tentang Field Study lingkungan pesisir.",
         ["B", "B", "A"],  # progress: ide, data: pilot, tim: sendiri
         ["A", "A", "B"],  # bidang: Sosial, jenis: Skripsi, target: jurnal nasional
         ["C", "C", "A"],  # topik: lingkungan, problem: ketergantungan, gap: studi wilayah
         ["A", "C", "A"],  # metode: kualitatif, pengumpulan: observasi, sumber: masyarakat
         ["A", "B", "B"],  # struktur: standar, kompleksitas: menengah, bagian: 5-7
         ["A", "B", "B"],  # sitasi: APA, referensi: 16-25, tahun: 5 tahun
         ["C", "B", "A"],  # visualisasi: peta, jumlah: 3-4, platform: Excel
         "Dampak Aktivitas Tambak Terhadap Kualitas Air dan Biodiversitas Pesisir di Jawa Tengah",
         ["A", "A", "B"],  # bahasa: Indonesia, nada: akademis, gaya: orang ketiga
         ["A", "A", "A"],  # tim: sendiri, supplementary: ada, biaya: tidak
     ]},

    # 7 ─ Ekonomi Econometric
    {"title": "Ekonomi — Econometric Analysis Master's",
     "turns": [
         "Halo, saya ingin membuat paper tentang Econometric Analysis.",
         ["C", "C", "A"],  # progress: draft, data: olahan, tim: sendiri
         ["A", "B", "B"],  # bidang: Sosial, jenis: Artikel Jurnal, target: jurnal nasional
         ["A", "A", "B"],  # topik: ekonomi, problem: akses pasar, gap: metode
         ["B", "B", "B"],  # metode: kuantitatif, pengumpulan: kuesioner, sumber: UMKM
         ["B", "B", "B"],  # struktur: IMRaD, kompleksitas: menengah, bagian: 5-7
         ["A", "B", "B"],  # sitasi: APA, referensi: 16-25, tahun: 5 tahun
         ["A", "B", "B"],  # visualisasi: tabel, jumlah: 3-4, platform: Python
         "Pengaruh Inflasi, Kurs, dan Suku Bunga terhadap Pertumbuhan Ekonomi Indonesia 2000-2023",
         ["A", "A", "B"],  # bahasa: Indonesia, nada: akademis, gaya: orang ketiga
         ["A", "A", "B"],  # tim: sendiri, supplementary: ada, biaya: ada
     ]},

    # 8 ─ Hukum Legal Analysis
    {"title": "Hukum — Legal Analysis Tesis",
     "turns": [
         "Halo, saya ingin membuat paper tentang Legal Analysis.",
         ["D", "C", "A"],  # progress: hampir selesai, data: olahan, tim: sendiri
         ["A", "B", "B"],  # bidang: Sosial, jenis: Artikel Jurnal, target: jurnal nasional
         ["A", "A", "A"],  # topik: ekonomi, problem: akses pasar, gap: studi wilayah
         ["A", "A", "C"],  # metode: kualitatif, pengumpulan: wawancara, sumber: dokumen
         ["B", "B", "B"],  # struktur: IMRaD, kompleksitas: menengah, bagian: 5-7
         ["C", "B", "B"],  # sitasi: Chicago, referensi: 16-25, tahun: 5 tahun
         ["B", "B", "A"],  # visualisasi: diagram, jumlah: 3-4, platform: Excel
         "Analisis Yuridis Perlindungan Hak Konsumen dalam Transaksi E-Commerce Berdasarkan UU ITE",
         ["A", "A", "B"],  # bahasa: Indonesia, nada: akademis, gaya: orang ketiga
         ["A", "A", "A"],  # tim: sendiri, supplementary: ada, biaya: tidak
     ]},

    # 9 ─ Komputer Machine Learning
    {"title": "Ilmu Komputer — ML Fraud Detection Scopus",
     "turns": [
         "Halo, saya mau buat paper machine learning untuk deteksi fraud.",
         ["A", "A", "A"],  # progress: ide, data: belum, tim: sendiri
         ["C", "B", "C"],  # bidang: Teknik, jenis: Artikel Jurnal, target: internasional
         ["D", "D", "B"],  # topik: digital, problem: kesenjangan, gap: metode
         ["B", "B", "B"],  # metode: kuantitatif, pengumpulan: kuesioner, sumber: UMKM
         ["B", "C", "C"],  # struktur: IMRaD, kompleksitas: kompleks, bagian: 8-10
         ["B", "C", "B"],  # sitasi: IEEE, referensi: 26-35, tahun: 5 tahun
         ["A", "C", "B"],  # visualisasi: tabel, jumlah: 5-6, platform: Python
         "Machine Learning untuk Deteksi Fraud Transaksi E-Commerce Menggunakan XGBoost dan SMOTE",
         ["B", "A", "B"],  # bahasa: Inggris, nada: akademis, gaya: orang ketiga
         ["A", "A", "B"],  # tim: sendiri, supplementary: ada, biaya: ada
     ]},

    # 10 ─ Kedokteran Clinical Study
    {"title": "Kedokteran — Clinical Study Diabetes Scopus",
     "turns": [
         "Halo, saya sudah mengumpulkan data klinis untuk penelitian diabetes.",
         ["B", "D", "B"],  # progress: outline, data: final, tim: 2-3
         ["B", "B", "C"],  # bidang: Kesehatan, jenis: Artikel Jurnal, target: internasional
         ["A", "A", "C"],  # topik: ekonomi, problem: akses, gap: dampak jangka panjang
         ["B", "B", "A"],  # metode: kuantitatif, pengumpulan: kuesioner, sumber: masyarakat
         ["B", "C", "B"],  # struktur: IMRaD, kompleksitas: kompleks, bagian: 5-7
         ["C", "C", "B"],  # sitasi: Vancouver, referensi: 26-35, tahun: 5 tahun
         ["A", "C", "B"],  # visualisasi: tabel, jumlah: 5-6, platform: Python
         "Glycemic Control and Quality of Life in Type 2 Diabetes: A 6-Month Prospective Study",
         ["B", "A", "B"],  # bahasa: Inggris, nada: akademis, gaya: orang ketiga
         ["B", "A", "B"],  # tim: 2-3, supplementary: ada, biaya: ada
     ]},

    # 11 ─ Fisika Computational Simulation
    {"title": "Fisika — Computational Simulation Jurnal Sinta 1",
     "turns": [
         "Halo, saya mau buat paper simulasi komputasi untuk jurnal Sinta 1.",
         ["B", "C", "A"],  # progress: outline, data: olahan, tim: sendiri
         ["C", "B", "C"],  # bidang: Teknik, jenis: Artikel Jurnal, target: Sinta 1
         ["B", "B", "B"],  # topik: material, problem: kekuatan, gap: metode
         ["B", "B", "A"],  # metode: kuantitatif, pengumpulan: kuesioner, sumber: masyarakat
         ["B", "C", "B"],  # struktur: IMRaD, kompleksitas: kompleks, bagian: 5-7
         ["B", "C", "B"],  # sitasi: IEEE, referensi: 26-35, tahun: 5 tahun
         ["A", "C", "B"],  # visualisasi: tabel, jumlah: 5-6, platform: Python
         "Simulasi Dinamika Molekular Material Graphene untuk Aplikasi Nano-elektronik",
         ["B", "A", "B"],  # bahasa: Inggris, nada: akademis, gaya: orang ketiga
         ["A", "A", "B"],  # tim: sendiri, supplementary: ada, biaya: ada
     ]},

    # 12 ─ Pertanian Agronomi
    {"title": "Pertanian — Agronomi Field Experiment",
     "turns": [
         "Saya peneliti pertanian, mau buat paper eksperimen lapangan pupuk organik.",
         ["B", "C", "B"],  # progress: outline, data: olahan, tim: 2-3
         ["C", "B", "B"],  # bidang: Pertanian, jenis: Artikel Jurnal, target: jurnal nasional
         ["C", "C", "A"],  # topik: lingkungan, problem: ketergantungan, gap: studi wilayah
         ["B", "C", "A"],  # metode: kuantitatif, pengumpulan: observasi, sumber: masyarakat
         ["B", "B", "B"],  # struktur: IMRaD, kompleksitas: menengah, bagian: 5-7
         ["A", "B", "B"],  # sitasi: APA, referensi: 16-25, tahun: 5 tahun
         ["A", "B", "A"],  # visualisasi: tabel, jumlah: 3-4, platform: Excel
         "Pengaruh Pupuk Organik Cair Berbasis Azolla terhadap Pertumbuhan dan Hasil Padi Sawah",
         ["A", "A", "B"],  # bahasa: Indonesia, nada: akademis, gaya: orang ketiga
         ["B", "A", "A"],  # tim: 2-3, supplementary: ada, biaya: tidak
     ]},

    # 13 ─ Arsitektur Urban Design
    {"title": "Arsitektur — Urban Design Research",
     "turns": [
         "Halo, saya mau tulis paper tentang desain urban kota berkelanjutan.",
         ["A", "A", "A"],  # progress: ide, data: belum, tim: sendiri
         ["E", "B", "B"],  # bidang: Lainnya, jenis: Artikel Jurnal, target: jurnal nasional
         ["B", "B", "A"],  # topik: digital, problem: kesenjangan, gap: studi wilayah
         ["A", "A", "C"],  # metode: kualitatif, pengumpulan: wawancara, sumber: dokumen
         ["A", "B", "B"],  # struktur: standar, kompleksitas: menengah, bagian: 5-7
         ["A", "B", "B"],  # sitasi: APA, referensi: 16-25, tahun: 5 tahun
         ["B", "B", "A"],  # visualisasi: diagram, jumlah: 3-4, platform: Excel
         "Integrasi Ruang Terbuka Hijau dalam Perancangan Kawasan Transit-Oriented Development",
         ["A", "A", "B"],  # bahasa: Indonesia, nada: akademis, gaya: orang ketiga
         ["A", "A", "A"],  # tim: sendiri, supplementary: ada, biaya: tidak
     ]},

    # 14 ─ Farmasi Drug Discovery
    {"title": "Farmasi — Drug Discovery Research",
     "turns": [
         "Saya sedang riset drug discovery untuk paper farmasi.",
         ["C", "C", "A"],  # progress: draft, data: olahan, tim: sendiri
         ["B", "B", "C"],  # bidang: Kesehatan, jenis: Artikel Jurnal, target: Sinta 1
         ["A", "A", "C"],  # topik: ekonomi, problem: akses, gap: dampak jangka panjang
         ["B", "B", "A"],  # metode: kuantitatif, pengumpulan: kuesioner, sumber: masyarakat
         ["B", "C", "B"],  # struktur: IMRaD, kompleksitas: kompleks, bagian: 5-7
         ["C", "C", "B"],  # sitasi: Vancouver, referensi: 26-35, tahun: 5 tahun
         ["A", "C", "B"],  # visualisasi: tabel, jumlah: 5-6, platform: Python
         "In Silico Molecular Docking Senyawa Flavonoid Kaempferol sebagai Inhibitor ACE2 pada SARS-CoV-2",
         ["B", "A", "B"],  # bahasa: Inggris, nada: akademis, gaya: orang ketiga
         ["A", "A", "B"],  # tim: sendiri, supplementary: ada, biaya: ada
     ]},

    # 15 ─ Sosiologi Kualitatif
    {"title": "Sosiologi — Qualitative Research Migrasi",
     "turns": [
         "Saya mau nulis paper kualitatif tentang pola migrasi tenaga kerja.",
         ["A", "A", "A"],  # progress: ide, data: belum, tim: sendiri
         ["A", "C", "A"],  # bidang: Sosial, jenis: Literature Review, target: ujian
         ["D", "B", "A"],  # topik: sosial, problem: partisipasi, gap: studi wilayah
         ["A", "A", "A"],  # metode: kualitatif, pengumpulan: wawancara, sumber: masyarakat
         ["A", "A", "B"],  # struktur: standar, kompleksitas: sederhana, bagian: 5-7
         ["A", "B", "B"],  # sitasi: APA, referensi: 16-25, tahun: 5 tahun
         ["B", "B", "A"],  # visualisasi: diagram, jumlah: 3-4, platform: Excel
         "Pola Migrasi dan Adaptasi Sosial Tenaga Kerja Indonesia di Malaysia: Studi Fenomenologi",
         ["A", "B", "B"],  # bahasa: Indonesia, nada: populer, gaya: orang ketiga
         ["A", "A", "A"],  # tim: sendiri, supplementary: ada, biaya: tidak
     ]},

    # 16 ─ Informatika NLP
    {"title": "Informatika — NLP Bahasa Indonesia",
     "turns": [
         "Halo, saya mau buat paper NLP untuk analisis sentimen bahasa Indonesia.",
         ["B", "B", "B"],  # progress: outline, data: pilot, tim: 2-3
         ["C", "B", "C"],  # bidang: Teknik, jenis: Artikel Jurnal, target: Sinta 1
         ["D", "D", "B"],  # topik: digital, problem: kesenjangan, gap: metode
         ["B", "B", "B"],  # metode: kuantitatif, pengumpulan: kuesioner, sumber: UMKM
         ["B", "C", "B"],  # struktur: IMRaD, kompleksitas: kompleks, bagian: 5-7
         ["B", "C", "B"],  # sitasi: IEEE, referensi: 26-35, tahun: 5 tahun
         ["A", "C", "B"],  # visualisasi: tabel, jumlah: 5-6, platform: Python
         "Analisis Sentimen Ulasan Produk E-Commerce Bahasa Indonesia Menggunakan IndoBERT",
         ["B", "A", "B"],  # bahasa: Inggris, nada: akademis, gaya: orang ketiga
         ["B", "A", "B"],  # tim: 2-3, supplementary: ada, biaya: ada
     ]},

    # 17 ─ Manajemen SDM
    {"title": "Manajemen — SDM Work From Home",
     "turns": [
         "Saya riset SDM tentang work from home dan produktivitas karyawan.",
         ["C", "C", "B"],  # progress: draft, data: olahan, tim: 2-3
         ["A", "B", "B"],  # bidang: Sosial, jenis: Artikel Jurnal, target: jurnal nasional
         ["A", "A", "B"],  # topik: ekonomi, problem: akses, gap: metode
         ["C", "B", "B"],  # metode: mixed, pengumpulan: kuesioner, sumber: UMKM
         ["B", "B", "B"],  # struktur: IMRaD, kompleksitas: menengah, bagian: 5-7
         ["A", "B", "B"],  # sitasi: APA, referensi: 16-25, tahun: 5 tahun
         ["A", "B", "A"],  # visualisasi: tabel, jumlah: 3-4, platform: Excel
         "Pengaruh Work From Home terhadap Produktivitas dan Kepuasan Kerja Karyawan Pasca Pandemi",
         ["A", "B", "B"],  # bahasa: Indonesia, nada: populer, gaya: orang ketiga
         ["B", "A", "A"],  # tim: 2-3, supplementary: ada, biaya: tidak
     ]},

    # 18 ─ Teknik Elektro IoT
    {"title": "Teknik Elektro — IoT Smart Agriculture",
     "turns": [
         "Saya develop sistem IoT untuk pertanian cerdas, mau buat paper.",
         ["B", "B", "B"],  # progress: outline, data: pilot, tim: 2-3
         ["C", "B", "C"],  # bidang: Teknik, jenis: Artikel Jurnal, target: internasional
         ["D", "D", "B"],  # topik: digital, problem: kesenjangan, gap: metode
         ["B", "B", "B"],  # metode: kuantitatif, pengumpulan: kuesioner, sumber: UMKM
         ["B", "C", "B"],  # struktur: IMRaD, kompleksitas: kompleks, bagian: 5-7
         ["B", "C", "B"],  # sitasi: IEEE, referensi: 26-35, tahun: 5 tahun
         ["D", "C", "B"],  # visualisasi: diagram algoritma, jumlah: 5-6, platform: Python
         "Design and Implementation of IoT-Based Smart Irrigation System Using Soil Moisture Sensing and MQTT Protocol",
         ["B", "A", "B"],  # bahasa: Inggris, nada: akademis, gaya: orang ketiga
         ["B", "A", "B"],  # tim: 2-3, supplementary: ada, biaya: ada
     ]},

    # 19 ─ Biologi Molekular
    {"title": "Biologi — Molecular Biology CRISPR",
     "turns": [
         "Saya mau buat paper eksperimen biologi molekular tentang CRISPR.",
         ["C", "D", "A"],  # progress: draft, data: final, tim: sendiri
         ["B", "B", "C"],  # bidang: Kesehatan, jenis: Artikel Jurnal, target: internasional
         ["A", "A", "C"],  # topik: ekonomi, problem: akses, gap: dampak jangka panjang
         ["B", "B", "A"],  # metode: kuantitatif, pengumpulan: kuesioner, sumber: masyarakat
         ["B", "C", "B"],  # struktur: IMRaD, kompleksitas: kompleks, bagian: 5-7
         ["C", "C", "B"],  # sitasi: Vancouver, referensi: 26-35, tahun: 5 tahun
         ["A", "C", "B"],  # visualisasi: tabel, jumlah: 5-6, platform: Python
         "CRISPR-Cas9 Mediated Knockout of BRCA1 Gene in MCF-7 Breast Cancer Cell Line",
         ["B", "A", "B"],  # bahasa: Inggris, nada: akademis, gaya: orang ketiga
         ["A", "A", "B"],  # tim: sendiri, supplementary: ada, biaya: ada
     ]},

    # 20 ─ Komunikasi Media Digital
    {"title": "Komunikasi — Media Digital & Misinformasi",
     "turns": [
         "Saya riset komunikasi tentang penyebaran misinformasi di media sosial.",
         ["A", "A", "A"],  # progress: ide, data: belum, tim: sendiri
         ["A", "C", "B"],  # bidang: Sosial, jenis: Literature Review, target: jurnal nasional
         ["D", "B", "A"],  # topik: sosial, problem: partisipasi, gap: studi wilayah
         ["A", "A", "A"],  # metode: kualitatif, pengumpulan: wawancara, sumber: masyarakat
         ["A", "B", "B"],  # struktur: standar, kompleksitas: menengah, bagian: 5-7
         ["A", "B", "B"],  # sitasi: APA, referensi: 16-25, tahun: 5 tahun
         ["B", "B", "A"],  # visualisasi: diagram, jumlah: 3-4, platform: Excel
         "Dinamika Penyebaran Misinformasi Kesehatan di Twitter Indonesia: Analisis Konten dan Jaringan",
         ["A", "B", "B"],  # bahasa: Indonesia, nada: populer, gaya: orang ketiga
         ["A", "A", "A"],  # tim: sendiri, supplementary: ada, biaya: tidak
     ]},

    # 21 ─ Akuntansi Forensik
    {"title": "Akuntansi — Forensic Accounting Fraud",
     "turns": [
         "Saya mau buat paper akuntansi forensik tentang deteksi fraud laporan keuangan.",
         ["B", "C", "B"],  # progress: outline, data: olahan, tim: 2-3
         ["A", "B", "B"],  # bidang: Sosial, jenis: Artikel Jurnal, target: jurnal nasional
         ["A", "A", "B"],  # topik: ekonomi, problem: akses, gap: metode
         ["B", "B", "B"],  # metode: kuantitatif, pengumpulan: kuesioner, sumber: UMKM
         ["B", "B", "B"],  # struktur: IMRaD, kompleksitas: menengah, bagian: 5-7
         ["A", "B", "B"],  # sitasi: APA, referensi: 16-25, tahun: 5 tahun
         ["A", "B", "A"],  # visualisasi: tabel, jumlah: 3-4, platform: Excel
         "Deteksi Financial Statement Fraud Menggunakan Beneish M-Score dan Altman Z-Score pada Perusahaan LQ-45",
         ["A", "A", "B"],  # bahasa: Indonesia, nada: akademis, gaya: orang ketiga
         ["B", "A", "B"],  # tim: 2-3, supplementary: ada, biaya: ada
     ]},

    # 22 ─ Geografi GIS (Contoh 30)
    {"title": "Geografi — GIS Analysis Tesis",
     "turns": [
         "Halo, saya ingin membuat paper tentang GIS Analysis.",
         "Path C",
         "Geography",
         "GIS Analysis",
         "Master's",
         "Pemetaan Kerentanan Banjir Menggunakan Analisis Multi-Kriteria dan SIG di DAS Citarum",
     ]},

    # 23 ─ Politik Policy Analysis (Contoh 28)
    {"title": "Ilmu Politik — Policy Analysis Tesis",
     "turns": [
         "Halo, saya ingin membuat paper tentang Policy Analysis.",
         "Path B",
         "Political Science",
         "Policy Analysis",
         "Master's",
         "Evaluasi Implementasi Kebijakan Program Kartu Prakerja terhadap Penyerapan Tenaga Kerja",
     ]},

    # 24 ─ Antropologi Etnografi (Contoh 29)
    {"title": "Antropologi — Ethnography PhD",
     "turns": [
         "Halo, saya ingin membuat paper tentang Ethnography.",
         "Path B",
         "Anthropology",
         "Ethnography",
         "PhD",
         "Ritual Adat dan Transformasi Identitas Budaya Suku Baduy dalam Era Digitalisasi",
     ]},

    # 25 ─ Teknik Mesin Simulation (Contoh 25)
    {"title": "Teknik Mesin — CFD Simulation Tesis",
     "turns": [
         "Halo, saya ingin membuat paper tentang Simulation CFD.",
         "Path C",
         "Mechanical Engineering",
         "Simulation",
         "Master's",
         "Analisis Aliran Fluida dan Perpindahan Panas pada Heat Exchanger Shell-and-Tube Menggunakan CFD",
     ]},

    # 26 ─ Kesehatan Masyarakat
    {"title": "Kesehatan Masyarakat — Epidemiologi Stunting",
     "turns": [
         "Saya riset kesehatan masyarakat tentang stunting pada balita.",
         "A",
         "A",
         "A",
         "C",
         "B",
         "B",
         "Faktor Risiko Stunting pada Balita 0-59 Bulan di Wilayah Rural Jawa Tengah: Studi Cross-Sectional",
     ]},

    # 27 ─ Linguistik Applied
    {"title": "Linguistik — Applied Linguistics EFL",
     "turns": [
         "Saya dosen bahasa Inggris mau buat paper tentang pembelajaran EFL.",
         "B",
         "B",
         "A",
         "D",
         "B",
         "B",
         "The Effect of Task-Based Language Teaching on EFL Learners Speaking Fluency at University Level",
     ]},

    # 28 ─ Psikologi Industri
    {"title": "Psikologi Industri — Burnout & Turnover Intention",
     "turns": [
         "Saya riset psikologi industri tentang burnout dan niat keluar kerja.",
         "A",
         "A",
         "A",
         "D",
         "B",
         "C",  # Sinta 1
         "Hubungan Burnout, Dukungan Sosial, dan Turnover Intention pada Perawat Rumah Sakit Swasta",
     ]},

    # 29 ─ Energi Terbarukan
    {"title": "Teknik Energi — Renewable Energy Optimization",
     "turns": [
         "Halo, saya mau buat paper optimasi sistem energi terbarukan hybrid.",
         "B",
         "C",
         "B",
         "B",
         "B",
         "D",  # Scopus
         "Optimal Sizing of Hybrid Photovoltaic-Wind-Battery System for Rural Electrification Using Genetic Algorithm",
     ]},

    # 30 ─ Full 9-phase dari awal sampai generate
    {"title": "FULL WORKFLOW — Informatika AI Healthcare Scopus (9 Fase)",
     "turns": [
         "saya mau buat paper full, bantu dari awal ya",
         # Fase 0
         "A",           # progress: ide awal
         "A",           # data: belum ada
         "A",           # individu
         # Fase 1
         "A",           # Ilmu Komputer
         "B",           # Research Paper
         "D",           # Scopus
         "Deep Learning untuk Prediksi Mortalitas Pasien ICU Menggunakan Data EHR Multivariate",
         # Fase 2
         "Prediksi mortalitas pasien ICU menggunakan rekam medis elektronik",
         "Model tradisional tidak bisa tangani data time-series multivariate ICU",
         "Belum ada model yang gabungkan LSTM dan attention untuk ICU lokal Indonesia",
         "Bagaimana LSTM-Attention meningkatkan akurasi prediksi mortalitas ICU?",
         "Bandingkan LSTM, GRU, Transformer pada dataset MIMIC-III",
         "ICU mortality prediction, deep learning, EHR, LSTM, attention mechanism",
         # Fase 3
         "A",           # Kuantitatif
         "LSTM dengan self-attention dan dropout regularization",
         "MIMIC-III critical care database (PhysioNet)",
         "53.000 pasien ICU, 17 variabel vital sign + lab",
         "Python, TensorFlow, scikit-learn, pandas",
         "A",           # Tidak perlu etik (data publik)
         # Fase 4
         "A",           # IEEE template
         "C",           # Tinggi Scopus Q3-Q4
         "A",           # 5 sections
         "D",           # Semua bab sama penting
         "Introduction, Related Work, Methodology, Experiments, Conclusion",
         # Fase 5
         "A",           # IEEE citation
         "C",           # 40-60 referensi
         "Paper kunci: Harutyunyan et al. 2019 MIMIC benchmarks",
         "A",           # 2019-2024
         "D",           # Zotero
         # Fase 6
         "A",           # Bar chart dan line chart
         "B",           # 5-8 gambar
         "A",           # CSV
         "A",           # Matplotlib
         # Fase 7
         "B",           # Bahasa Inggris
         "A",           # Formal akademik
         "A",           # Third person passive
         "B",           # Kualitas > kecepatan
         "A",           # Perlu cek plagiarisme
         # Fase 8
         "Ahmad Fauzan, Muhammad Rizky",
         "Tidak ada konflik kepentingan, data MIMIC-III sudah licensed",
         "A",           # APC < Rp 5 juta
         "B",           # 2-4 bulan
         "B",           # Ada reviewer internal (pembimbing)
         "A",           # DOCX + PDF
     ]},
]


# ─── run one scenario ─────────────────────────────────────────────────────
def run_scenario(idx: int, scenario: dict, be: dict) -> bool:
    title  = scenario["title"]
    turns  = scenario["turns"]
    outfile = TERMINAL_DIR / f"{idx}.txt"

    print(bold(f"\n{'='*60}"))
    print(bold(f"[{idx}/30] {title}"))
    print(bold(f"{'='*60}"))

    sess = ConvSession(be, title)
    ok   = True
    turn_idx = 0

    while turn_idx < len(turns):
        user_msg = turns[turn_idx]
        turn_idx += 1
        
        try:
            ai_reply, num_questions = sess.send(user_msg)
            
            # If AI asked multiple questions, combine next N answers
            if num_questions > 1 and turn_idx < len(turns):
                answers = []
                for _ in range(min(num_questions, len(turns) - turn_idx + 1)):
                    if turn_idx < len(turns):
                        answers.append(turns[turn_idx])
                        turn_idx += 1
                
                # Send combined answers
                if answers:
                    combined = ", ".join(answers)
                    ai_reply2, _ = sess.send(combined)
                    
        except Exception as e:
            err = f"\n[ERROR turn {turn_idx}]: {e}"
            sess.log.append(err)
            print(red(err))
            ok = False
            break

        # Quick sanity: did AI write plain questions (bad) or use tool (good)?
        has_plain_q = bool(re.search(r'\[OPSI\]|\[A\]\s|\*\*\[0\.', ai_reply))
        if has_plain_q:
            warn = "  ⚠ WARN: AI wrote questions as plain text (should use tool)"
            sess.log.append(warn)
            print(yellow(warn))
            ok = False

    # Final summary
    ans_count = len(sess.wf.answers)
    phase_now = sess.wf.phase
    status    = green("✓ SELESAI") if phase_now in ("9","done") else yellow(f"~ Phase {phase_now}")
    summary   = f"\n{'─'*40}\nHasil: {status}  |  Jawaban: {ans_count}  |  File: {outfile.name}"
    sess.log.append(summary)
    print(summary)

    sess.save(outfile)
    return ok


# ─── main ─────────────────────────────────────────────────────────────────
def main():
    args = sys.argv[1:]

    if "--list" in args:
        for i, s in enumerate(SCENARIOS, 1):
            print(f"  {i:2d}. {s['title']}")
        return

    print(bold("Memuat backend modules..."), end=" ", flush=True)
    try:
        be = _load_be()
        print(green("OK"))
    except Exception as e:
        print(red(f"GAGAL: {e}"))
        import traceback; traceback.print_exc()
        sys.exit(1)

    print(f"  Model : {dim(CHAT_MODEL)} @ {dim(API_BASE)}")
    print(f"  Output: {dim(str(TERMINAL_DIR))}")

    # Parse range args
    if args and args[0].isdigit():
        lo = int(args[0])
        hi = int(args[1]) if len(args) > 1 and args[1].isdigit() else lo
    else:
        lo, hi = 1, 30

    lo = max(1, min(lo, 30))
    hi = max(lo, min(hi, 30))

    total = 0
    passed = 0
    for idx in range(lo, hi + 1):
        scenario = SCENARIOS[idx - 1]
        ok = run_scenario(idx, scenario, be)
        total += 1
        if ok:
            passed += 1

    print(bold(f"\n{'='*60}"))
    print(bold(f"SELESAI: {green(str(passed))}/{total} skenario berhasil"))
    if passed < total:
        failed_files = [f"{TERMINAL_DIR}/{i}.txt" for i in range(lo, hi+1)]
        print(yellow(f"Cek file .txt untuk detail error"))
    print(bold(f"{'='*60}"))


if __name__ == "__main__":
    main()
