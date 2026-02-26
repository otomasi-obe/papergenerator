"""
Paper Generator - Backend API Server
=====================================
Flask API for AI-powered academic paper generation and DOCX export.
Supports IEEE conference paper format.
"""

import os
import re
import sys
import json
import uuid
import time
import base64
import logging
import traceback
import threading
from pathlib import Path
from datetime import datetime

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
import httpx

from docx_generator import generate_ieee_docx

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# ─── Logging Setup ──────────────────────────────────────────────────────────
LOG_FILE = Path(__file__).parent / "app.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)
log.info("=" * 60)
log.info("Backend started")

# Configuration
UPLOAD_FOLDER = Path(__file__).parent / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)
EXPORT_FOLDER = Path(__file__).parent / "exports"
EXPORT_FOLDER.mkdir(exist_ok=True)

# OpenAI client
openai_client = None
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ─── In-Memory Job Store ──────────────────────────────────────────────────────
# Stores background generation jobs: job_id -> { status, result, error, started_at }
_jobs: dict = {}
_jobs_lock = threading.Lock()

def _job_set(job_id: str, data: dict):
    with _jobs_lock:
        _jobs[job_id] = data

def _job_get(job_id: str) -> dict | None:
    with _jobs_lock:
        return _jobs.get(job_id)

def _job_pop(job_id: str) -> dict | None:
    with _jobs_lock:
        return _jobs.pop(job_id, None)


def get_openai_client():
    global openai_client
    if openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "sk-your-actual-api-key":
            raise Exception("OPENAI_API_KEY not configured. Please set it in backend/.env")
        # Use per-operation timeouts via httpx.Timeout:
        #   connect=30s, read=1200s (20 min for full paper), write=60s
        # max_retries=0 prevents compounding timeouts on retry
        openai_client = OpenAI(
            api_key=api_key,
            timeout=httpx.Timeout(connect=30.0, read=1200.0, write=60.0, pool=10.0),
            max_retries=0,
        )
    return openai_client


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    has_key = bool(os.getenv("OPENAI_API_KEY")) and os.getenv("OPENAI_API_KEY") != "sk-your-actual-api-key"
    return jsonify({
        "status": "ok",
        "model": OPENAI_MODEL,
        "hasApiKey": has_key,
        "timestamp": datetime.now().isoformat()
    })


# ─── AI Generate ─────────────────────────────────────────────────────────────

@app.route("/api/generate", methods=["POST"])
def generate():
    """
    Generate or edit paper content with AI.
    Expects JSON: { prompt: string, lastText: string, section: string }
    - prompt: the user's instruction
    - lastText: the current text content of the section being edited
    - section: which section is being edited (title, abstract, introduction, etc.)
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        prompt = data.get("prompt", "")
        last_text = data.get("lastText", "")
        paper_context = data.get("paperContext", {})

        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400

        client = get_openai_client()

        section = data.get("section", "").lower()
        
        # Dynamic system prompts based on section type
        prompts_by_section = {
            "title": """You are an IEEE conference paper title writer. Generate a concise, specific paper title (max 15 words) 
that clearly indicates the research contribution. Include key technical terms and method names if relevant. Return ONLY the title.""",
            
            "abstract": """You are an IEEE conference paper writer. Generate a 150-200 word abstract following IEEE format.
Start with problem statement, then propose method, then results. Include quantitative metrics if available.
For formulas use $..$ notation. Return ONLY the abstract text.""",
            
            "introduction": """You are an IEEE conference researcher. Write an INTRODUCTION section (200-300 words) that:
1) Motivates the problem with background
2) Identifies the research gap
3) States contributions clearly
Include citations as [1], [2], etc. Use $$formula$$ for displayed equations. Write naturally, academically.""",
            
            "methodology": """You are a systems researcher. Write a METHODOLOGY/APPROACH section that describes:
1) Problem formulation (with equations if needed)
2) Proposed method/algorithm (with formulas: use $x$ for inline, $$formula$$ for display)
3) Implementation details
Use IEEE notation and cite related work as [1], [2]. Be technical and specific.""",
            
            "results": """You are a research scientist. Write EXPERIMENTAL RESULTS section:
1) Datasets/benchmarks used
2) Evaluation metrics with values (e.g., "achieves 92.5% accuracy")
3) Comparison with baselines [1][2]
4) Analysis and insights
Include numerical results. Cite properly. Be quantitative.""",
            
            "conclusion": """You are an academic writer. Write CONCLUSION section (100-150 words):
1) Summarize key contributions
2) Highlight achieved metrics
3) Mention future work
Keep it clear and formal. No markdown.""",
            
            "acknowledgment": """You are writing paper acknowledgments. Write 2-3 sentences thanking:
- Funding agencies (if any mention XXXX)
- Collaborators/advisors
- Data/resource providers
Format: "We thank X for Y support. We gratefully acknowledge Z."
Keep it professional and concise.""",
        }
        
        base_prompt = prompts_by_section.get(section, 
            """You are an expert academic writer for IEEE papers. Generate content for the specified section.
            Use LaTeX notation for formulas ($..$ inline, $$...$$ display). Cite with [1], [2], etc format.
            Write formally and technically. Return ONLY the content.""")
        
        system_prompt = base_prompt

        messages = [{"role": "system", "content": system_prompt}]

        # Build context message
        context_parts = []
        if paper_context:
            context_parts.append(f"Paper title: {paper_context.get('title', 'Untitled')}")
            if paper_context.get('authors'):
                context_parts.append(f"Authors: {json.dumps(paper_context['authors'])}")
            if paper_context.get('abstract'):
                context_parts.append(f"Abstract: {paper_context['abstract'][:500]}")

        if last_text:
            context_parts.append(f"\n--- Current content of '{section}' section ---\n{last_text}\n--- End of current content ---")

        if context_parts:
            messages.append({"role": "user", "content": "\n".join(context_parts)})
            messages.append({"role": "assistant", "content": "I understand the context. What would you like me to do?"})

        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages
        )

        result = response.choices[0].message.content
        return jsonify({
            "success": True,
            "content": result,
            "model": OPENAI_MODEL,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ─── Generate Full Paper ─────────────────────────────────────────────────────

def _run_generate_full_job(job_id: str, prompt: str):
    """
    Background thread: calls OpenAI, parses result, stores in _jobs.
    The HTTP endpoint returns immediately with job_id; frontend polls /api/job/<id>.
    """
    t_start = time.time()
    log.info("[job:%s] STEP 1: background thread started, prompt=%r", job_id, prompt[:80])
    try:
        client = get_openai_client()

        system_prompt = "You are an expert IEEE conference paper author. Generate a complete IEEE conference paper as valid JSON only — no markdown, no text outside the JSON object."

        user_message = f"""Generate a complete IEEE conference paper on this topic: {prompt}

Return ONLY the JSON object below — no markdown, no code fences, no text outside JSON.
All LaTeX in JSON strings: double-escape backslashes (\\\\alpha, \\\\frac{{a}}{{b}}, \\\\mathbf{{X}}).
Inline math: $...$  |  Display equation: $$...$$ on its own paragraph line in content strings.
equations[] array: raw LaTeX only, no $ delimiters.

{{
  "title": "Specific technical title max 15 words including proposed method acronym",
  "authors": [
    {{"name": "Firstname Lastname", "affiliation": "Dept of X, University Y", "location": "City, Country", "email": "a@b.edu"}},
    {{"name": "Second Author",      "affiliation": "School of Z, Institute W", "location": "City, Country", "email": "c@d.edu"}}
  ],
  "abstract": "150-200 words: problem, method key innovations, quantitative result (X% metric on Dataset, +Y% vs baseline), impact.",
  "keywords": ["kw1","kw2","kw3","kw4","kw5","kw6"],
  "sections": [
    {{"id":"id-sec1","number":"I","title":"INTRODUCTION","content":"400-500 words. Context, prior work [1][2][3], problem gap, contributions (\\n• ...), paper organization.","subsections":[]}},
    {{"id":"id-sec2","number":"II","title":"RELATED WORK","content":"100-150 word overview of the three threads.","subsections":[
      {{"id":"id-sub2a","letter":"A","title":"[Category A relevant to topic]","content":"250-350 words reviewing 5+ works chronologically with limitations.","numberedItems":[]}},
      {{"id":"id-sub2b","letter":"B","title":"[Category B relevant to topic]","content":"250-350 words.","numberedItems":[]}},
      {{"id":"id-sub2c","letter":"C","title":"[Category C relevant to topic]","content":"200-300 words.","numberedItems":[]}}
    ]}},
    {{"id":"id-sec3","number":"III","title":"PROPOSED METHOD","content":"80-120 word overview of the full framework referencing Fig. 1.","subsections":[
      {{"id":"id-sub3a","letter":"A","title":"Problem Formulation","content":"200-300 words. Formally define input/output with 2 display equations $$...$$ each explained.","numberedItems":[]}},
      {{"id":"id-sub3b","letter":"B","title":"System Architecture","content":"300-400 words referencing Fig. 1 and Fig. 2 with inline math and 1 display equation.","numberedItems":[]}},
      {{"id":"id-sub3c","letter":"C","title":"[Key Proposed Module]","content":"300-400 words with 1-2 display equations.","numberedItems":[]}},
      {{"id":"id-sub3d","letter":"D","title":"Loss Function","content":"200-300 words with total loss display equation $$\\\\mathcal{{L}}_{{\\\\text{{total}}}} = ...$$.","numberedItems":[]}}
    ]}},
    {{"id":"id-sec4","number":"IV","title":"EXPERIMENTAL RESULTS","content":"80-100 word overview.","subsections":[
      {{"id":"id-sub4a","letter":"A","title":"Experimental Setup","content":"200-300 words: datasets, splits, augmentation, hardware referencing Table I.","numberedItems":[]}},
      {{"id":"id-sub4b","letter":"B","title":"Performance Evaluation","content":"250-350 words comparing Table II row-by-row with specific numbers.","numberedItems":[]}},
      {{"id":"id-sub4c","letter":"C","title":"Ablation Study","content":"200-300 words analyzing Table III component-by-component.","numberedItems":[]}}
    ]}},
    {{"id":"id-sec5","number":"V","title":"CONCLUSION","content":"150-200 words: summary, key metric, limitation, future work.","subsections":[]}}
  ],
  "acknowledgment": "2-3 sentences: specific funding agency, grant number, computational resources.",
  "references": [
    {{"id":1,"text":"IEEE format: Author(s), 'Title,' Venue, Year, pp., doi."}},
    {{"id":2,"text":"..."}}
  ],
  "figures": [
    {{"id":"figure-1","caption":"Fig. 1. Overall architecture of the proposed method showing encoder, key module, and decoder.","filename":"","url":""}},
    {{"id":"figure-2","caption":"Fig. 2. Detailed structure of the proposed [Key Module].","filename":"","url":""}},
    {{"id":"figure-3","caption":"Fig. 3. Qualitative results: input, ground truth, prediction.","filename":"","url":""}},
    {{"id":"figure-4","caption":"Fig. 4. Accuracy vs. efficiency trade-off compared to state-of-the-art.","filename":"","url":""}}
  ],
  "tables": [
    {{"id":"table-1","caption":"TABLE I. Training Configuration","headers":["Setting","Value"],"rows":[["Dataset","<name>"],["Optimizer","SGD (momentum=0.9)"],["Initial LR","<value>"],["LR Schedule","Poly (power=0.9)"],["Batch Size","<value>"],["Epochs","<value>"],["GPU","<model>"],["Framework","PyTorch"]]}},
    {{"id":"table-2","caption":"TABLE II. Comparison with State-of-the-Art","headers":["Method","Backbone","Params (M)","FLOPs (G)","Metric (%)","FPS"],"rows":[["Method1 [1]","<backbone>","<params>","<flops>","<metric>","<fps>"],["Method2 [2]","<backbone>","<params>","<flops>","<metric>","<fps>"],["Method3 [3]","<backbone>","<params>","<flops>","<metric>","<fps>"],["Method4 [4]","<backbone>","<params>","<flops>","<metric>","<fps>"],["Method5 [5]","<backbone>","<params>","<flops>","<metric>","<fps>"],["Method6 [6]","<backbone>","<params>","<flops>","<metric>","<fps>"],["Method7 [7]","<backbone>","<params>","<flops>","<metric>","<fps>"],["Proposed (Ours)","Custom","<params>","<flops>","<metric>","<fps>"]]}},
    {{"id":"table-3","caption":"TABLE III. Ablation Study","headers":["Config","Module A","Module B","Module C","Params (M)","Metric (%)"],"rows":[["Baseline","✗","✗","✗","<p>","<m>"],["+ Module A","✓","✗","✗","<p>","<m>"],["+ Module B","✓","✓","✗","<p>","<m>"],["Full Model","✓","✓","✓","<p>","<m>"]]}}
  ],
  "equations": [
    {{"id":"eq-1","latex":"<raw LaTeX eq 1>","number":1}},
    {{"id":"eq-2","latex":"<raw LaTeX eq 2>","number":2}},
    {{"id":"eq-3","latex":"<raw LaTeX eq 3>","number":3}},
    {{"id":"eq-4","latex":"<raw LaTeX eq 4>","number":4}},
    {{"id":"eq-5","latex":"<raw LaTeX eq 5>","number":5}},
    {{"id":"eq-6","latex":"<raw LaTeX eq 6>","number":6}}
  ]
}}

Requirements:
- 12+ real IEEE-format references (2018-2025)
- Fill ALL table rows with topic-realistic numbers
- Invent specific method acronym fitting the topic
- All LaTeX: double-escaped in JSON (\\\\alpha not \\alpha)
- Topic for this paper: {prompt}"""

        log.info("[job:%s] STEP 2: Calling OpenAI model=%s", job_id, OPENAI_MODEL)
        t_openai_start = time.time()

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
        )

        openai_duration = time.time() - t_openai_start
        usage = response.usage
        log.info(
            "[job:%s] STEP 3: OpenAI responded in %.1fs | tokens=%d",
            job_id, openai_duration, usage.total_tokens
        )

        result_text = response.choices[0].message.content.strip()

        # Save raw response for debugging
        try:
            (Path(__file__).parent / "last_openai_raw.txt").write_text(result_text, encoding="utf-8")
        except Exception:
            pass

        # Strip markdown fences if present
        if result_text.startswith("```"):
            result_text = re.sub(r'^```(?:json)?\s*', '', result_text)
            result_text = re.sub(r'\s*```$', '', result_text.rstrip())

        # Parse JSON
        paper_data = None
        try:
            paper_data = json.loads(result_text)
        except json.JSONDecodeError as e:
            log.warning("[job:%s] direct json.loads failed: %s — trying brace extraction", job_id, e)
            first_brace = result_text.find('{')
            last_brace = result_text.rfind('}')
            if first_brace != -1 and last_brace > first_brace:
                paper_data = json.loads(result_text[first_brace:last_brace + 1])
            else:
                raise ValueError("No JSON object found in OpenAI response")

        if not isinstance(paper_data, dict):
            raise ValueError(f"Parsed value is not a dict: {type(paper_data)}")

        # Normalise schema to match frontend expectations
        paper_data.setdefault("authors", [{"name": "Author Name", "affiliation": "Department, University", "location": "City, Country", "email": "author@example.com"}])
        paper_data.setdefault("keywords", [])
        paper_data.setdefault("sections", [])
        paper_data.setdefault("acknowledgment", "")
        paper_data.setdefault("references", [])
        paper_data.setdefault("figures", [])
        paper_data.setdefault("tables", [])
        paper_data.setdefault("equations", [])

        for auth in paper_data["authors"]:
            auth.setdefault("name", ""); auth.setdefault("affiliation", "")
            auth.setdefault("location", ""); auth.setdefault("email", "")

        for i, sec in enumerate(paper_data["sections"]):
            sec.setdefault("id", f"id-sec{i+1}"); sec.setdefault("number", "")
            sec.setdefault("title", ""); sec.setdefault("content", "")
            sec.setdefault("subsections", [])
            for j, sub in enumerate(sec["subsections"]):
                sub.setdefault("id", f"id-sub{i+1}{chr(97+j)}")
                sub.setdefault("letter", chr(65 + j))
                sub.setdefault("title", ""); sub.setdefault("content", "")
                sub.setdefault("numberedItems", [])

        for i, fig in enumerate(paper_data["figures"]):
            fig.setdefault("id", f"figure-{i+1}"); fig.setdefault("caption", f"Fig. {i+1}. ")
            fig.setdefault("filename", ""); fig.setdefault("url", "")

        for i, tbl in enumerate(paper_data["tables"]):
            tbl.setdefault("id", f"table-{i+1}"); tbl.setdefault("caption", f"TABLE {i+1}. ")
            tbl.setdefault("headers", []); tbl.setdefault("rows", [])

        for i, eq in enumerate(paper_data["equations"]):
            eq.setdefault("id", f"eq-{i+1}"); eq.setdefault("latex", ""); eq.setdefault("number", i + 1)

        elapsed = time.time() - t_start
        log.info("[job:%s] DONE in %.1fs — storing result", job_id, elapsed)
        _job_set(job_id, {
            "status": "done",
            "result": paper_data,
            "usage": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            },
            "elapsed": int(elapsed),
        })

    except Exception as e:
        elapsed = time.time() - t_start
        err_type = type(e).__name__
        err_str = str(e)
        timeout_flag = "timeout" in err_type.lower() or "timeout" in err_str.lower() or "timed out" in err_str.lower()
        log.error("[job:%s] FAILED after %.1fs (%s): %s", job_id, elapsed, err_type, e, exc_info=True)
        _job_set(job_id, {
            "status": "error",
            "error": f"Generation timed out after {int(elapsed)}s. Try a shorter topic." if timeout_flag else err_str,
            "timeout": timeout_flag,
        })


@app.route("/api/generate-full", methods=["POST"])
def generate_full():
    """
    Start full paper generation as a background job.
    Returns { job_id } immediately — poll /api/job/<job_id> for status.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400

        # Validate API key early so the user gets an instant error
        get_openai_client()

        job_id = uuid.uuid4().hex[:12]
        _job_set(job_id, {"status": "pending", "started_at": time.time()})

        thread = threading.Thread(target=_run_generate_full_job, args=(job_id, prompt), daemon=True)
        thread.start()

        log.info("[generate-full] job_id=%s started for prompt=%r", job_id, prompt[:80])
        return jsonify({"success": True, "job_id": job_id})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/job/<job_id>", methods=["GET"])
def get_job_status(job_id):
    """
    Poll the status of a background generation job.
    Returns:
      { status: 'pending', elapsed: int }
      { status: 'done',    success: true, paper: {...}, usage: {...}, elapsed: int }
      { status: 'error',   error: str }
    """
    job = _job_get(job_id)
    if job is None:
        return jsonify({"error": "Job not found or already retrieved"}), 404

    elapsed = int(time.time() - job.get("started_at", time.time())) if "started_at" in job else job.get("elapsed", 0)

    if job["status"] == "pending":
        return jsonify({"status": "pending", "elapsed": elapsed})

    elif job["status"] == "done":
        # Keep the result in the store for 5 minutes so that a retry after a missed
        # response does not return 404.  Use threading.Timer for deferred cleanup
        # and only schedule it once (guard against duplicate timers on repeated polls).
        if not job.get("_cleanup_scheduled"):
            job["_cleanup_scheduled"] = True
            _job_set(job_id, job)
            threading.Timer(300, _job_pop, args=(job_id,)).start()
        return jsonify({
            "status": "done",
            "success": True,
            "paper": job["result"],
            "usage": job.get("usage", {}),
            "elapsed": job.get("elapsed", elapsed),
        })

    else:  # error
        _job_pop(job_id)   # clean up
        return jsonify({
            "status": "error",
            "error": job.get("error", "Unknown error"),
            "timeout": job.get("timeout", False),
        })




# ─── Image Upload ─────────────────────────────────────────────────────────────

@app.route("/api/upload-image", methods=["POST"])
def upload_image():
    """Upload an image file for the paper."""
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        # Generate unique filename
        ext = Path(file.filename).suffix.lower()
        if ext not in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg"]:
            return jsonify({"error": "Invalid image format. Supported: png, jpg, jpeg, gif, bmp, svg"}), 400

        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = UPLOAD_FOLDER / filename
        file.save(str(filepath))

        return jsonify({
            "success": True,
            "filename": filename,
            "url": f"/api/images/{filename}",
            "originalName": file.filename
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/images/<filename>", methods=["GET"])
def get_image(filename):
    """Serve uploaded image."""
    filepath = UPLOAD_FOLDER / filename
    if not filepath.exists():
        return jsonify({"error": "Image not found"}), 404
    return send_file(str(filepath))


# ─── Export DOCX ──────────────────────────────────────────────────────────────

@app.route("/api/export", methods=["POST"])
def export_docx():
    """
    Export paper to DOCX in IEEE conference format.
    Expects the full paper JSON structure.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No paper data provided"}), 400

        paper = data.get("paper", data)

        # Generate DOCX
        filename = f"paper_{uuid.uuid4().hex[:8]}.docx"
        filepath = EXPORT_FOLDER / filename

        generate_ieee_docx(paper, str(filepath), str(UPLOAD_FOLDER))

        return send_file(
            str(filepath),
            as_attachment=True,
            download_name=f"{paper.get('title', 'paper')[:50]}.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ─── Save/Load Paper ─────────────────────────────────────────────────────────

@app.route("/api/papers", methods=["POST"])
def save_paper():
    """Save paper data to a JSON file."""
    try:
        data = request.get_json()
        paper_id = data.get("id", uuid.uuid4().hex[:8])
        papers_dir = Path(__file__).parent / "papers"
        papers_dir.mkdir(exist_ok=True)

        filepath = papers_dir / f"{paper_id}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return jsonify({"success": True, "id": paper_id})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/papers/<paper_id>", methods=["GET"])
def load_paper(paper_id):
    """Load paper data from JSON file."""
    try:
        filepath = Path(__file__).parent / "papers" / f"{paper_id}.json"
        if not filepath.exists():
            return jsonify({"error": "Paper not found"}), 404

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        return jsonify(data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/papers", methods=["GET"])
def list_papers():
    """List all saved papers."""
    try:
        papers_dir = Path(__file__).parent / "papers"
        papers_dir.mkdir(exist_ok=True)

        papers = []
        for f in papers_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    papers.append({
                        "id": f.stem,
                        "title": data.get("title", "Untitled"),
                        "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                    })
            except:
                pass

        papers.sort(key=lambda x: x["modified"], reverse=True)
        return jsonify({"papers": papers})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/papers/<paper_id>", methods=["DELETE"])
def delete_paper(paper_id):
    """Delete a saved paper."""
    try:
        filepath = Path(__file__).parent / "papers" / f"{paper_id}.json"
        if filepath.exists():
            filepath.unlink()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    print(f"🚀 Paper Generator API running on http://localhost:{port}")
    print(f"📝 Model: {OPENAI_MODEL}")
    print(f"🔑 API Key: {'configured' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}")
    # use_reloader=False prevents the debug reloader from killing in-flight
    # long-running requests (e.g. OpenAI API calls) when source files change.
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False, threaded=True)
