"""
Job blueprint — async paper generation backed by Redis + RQ, with SSE progress
streaming and a 'resume' endpoint so the UI can re-attach to a running job after
the user reloads or switches papers (rofiq.txt #4).

Endpoints
---------
POST /api/papers/<paper_id>/generate
    Enqueue a generate-paper job. Returns {job_id}.

GET  /api/jobs/<job_id>
    Job status snapshot (status/progress/stage/error).

GET  /api/jobs/<job_id>/stream         (SSE)
    Server-Sent Events stream of {stage, percent, partial} until job terminates.

GET  /api/papers/<paper_id>/active-jobs
    List active jobs (queued|running) for this paper, so the UI can resume.

GET  /api/papers/<paper_id>/ai-jobs/active
    Single active job (queued|running|paused) for the paper, or null.

POST /api/jobs/<job_id>/cancel
POST /api/ai-jobs/<job_id>/cancel
    Best-effort cancel (sets status=cancelled, worker checks the flag).

POST /api/ai-jobs/<job_id>/resume
    Re-enqueue with resume_state read from the row's checkpoint.

POST /api/ai-jobs/<job_id>/retry-section
    Body {stage}. Removes the stage from chunks_done + matching section from
    partial_paper.sections, then re-enqueues so just that chunk regenerates.

GET  /api/me/ai-jobs/recent
    Filterable inbox of the user's recent jobs (badge + recently-done lookup).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
import logging
from typing import Optional

import redis
from flask import Blueprint, Response, jsonify, request, stream_with_context
from flask_jwt_extended import get_jwt_identity, jwt_required, verify_jwt_in_request

from utils.database.models import AiJob, Paper, ImageGenJob, db, safe_commit

jobs = Blueprint("jobs", __name__)

log = logging.getLogger(__name__)


def _detect_paper_kind(paper_data: dict) -> str:
    """Detect paper type: 'regular' or 'review'.

    REVIEW mode indicators (from prompt rules):
      - section2 title contains 'review methodology' / 'metodologi review'
      - section3+ are 'TOPIC DISCUSSION' (not 'METHODOLOGY'/'RESULTS')
      - section3+ subsections lack typical metodologi/results structure

    REGULAR mode indicators:
      - section2 = LITERATURE REVIEW
      - section3 = METHODOLOGY
      - section4 = RESULTS AND DISCUSSION

    Returns 'review' or 'regular' (default).
    """
    if not isinstance(paper_data, dict):
        return "regular"

    import re as _re

    # Check section2 title for review signals
    s2 = paper_data.get("section2", {})
    s2_title = str(s2.get("title", "") if isinstance(s2, dict) else "").lower()
    if any(kw in s2_title for kw in ("review methodology", "metodologi review", "systematic review")):
        return "review"

    # Check section3 structure: if it has subsections that look like TOPIC DISCUSSION
    # rather than METHODOLOGY, it's a review
    s3 = paper_data.get("section3", {})
    if isinstance(s3, dict):
        s3_title = str(s3.get("title", "")).lower()
        s3_content = s3.get("content", {})
        # Count subsections that are topic-like
        if isinstance(s3_content, dict):
            topic_count = 0
            methodology_count = 0
            for k in s3_content:
                if _re.match(r'section3[a-z]$', k):
                    sub = s3_content[k]
                    if isinstance(sub, dict):
                        sub_title = str(sub.get("title", "")).lower()
                        if any(kw in sub_title for kw in ("method", "metode", "experiment")):
                            methodology_count += 1
                        else:
                            topic_count += 1
            # Only consider review if there are 3+ topic subsections and no methodology subsections
            if topic_count >= 3 and methodology_count == 0:
                return "review"

    # Check section4: in review mode, sec4 is also a topic discussion
    s4 = paper_data.get("section4", {})
    if isinstance(s4, dict):
        s4_title = str(s4.get("title", "")).lower()
        if any(kw in s4_title for kw in ("results", "result", "hasil")):
            return "regular"

    # Default: regular
    return "regular"


def _collect_gambar_prompts(paper_data: dict, paper_kind: Optional[str] = None) -> list[dict]:
    """Walk ALL sections and collect gambar prompts for AI image generation.

    ALL gambar items with filled Prompt across ALL sections → image_gen (Gemini).
    No data tools pipeline — everything goes through image generation.
    Section 4 chart data prompts are sent to image_gen directly.

    Args:
        paper_data: Full paper JSON.
        paper_kind: 'regular' or 'review'. Ignored — all papers use image_gen.

    Returns a list of dicts: {prompt, image_number, title, original_path}.

    Filters:
      - Gambar with existing valid Path → skipped (no regeneration)
      - Empty prompts → skipped
    """
    if paper_kind is None:
        paper_kind = _detect_paper_kind(paper_data)

    prompts = []
    if not isinstance(paper_data, dict):
        return prompts

    def walk(obj, current_section=None):
        if isinstance(obj, dict):
            if obj.get("id") == "gambar":
                p = obj.get("Prompt") or obj.get("prompt") or ""
                # Skip if already has a valid image file (uploaded)
                existing_path = str(obj.get("Path") or obj.get("path") or "").strip()
                if existing_path and os.path.isabs(existing_path) and os.path.exists(existing_path):
                    return  # skip — already has a valid image
                if not p.strip():
                    return  # skip empty prompts
                # ALL gambar with prompts → image_gen (including section 4 chart data)
                prompts.append({
                    "prompt": p.strip(),
                    "image_number": obj.get("ImageNumber") or obj.get("imageNumber") or "",
                    "title": obj.get("Title") or obj.get("title") or "",
                    "original_path": obj.get("Path") or obj.get("path") or "",
                    "_section": current_section or "",
                })
            for k, v in obj.items():
                child_section = current_section
                if isinstance(k, str):
                    m = re.match(r'(section\d+)[a-z]?$', k)
                    if m:
                        child_section = m.group(1)
                    if k in ("sections", "subsections") and isinstance(v, list) and current_section is None:
                        if k == "sections":
                            for i, item in enumerate(v):
                                section_num = i + 1
                                walk(item, current_section=f"section{section_num}")
                            continue
                walk(v, current_section=child_section)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, current_section=current_section)

    walk(paper_data)
    # Deduplicate by prompt text (keep first occurrence)
    seen = set()
    unique = []
    for item in prompts:
        if item["prompt"] not in seen:
            seen.add(item["prompt"])
            unique.append(item)
    return unique

def _verify_data_integrity(paper_data: dict, data_texts: list[str], paper_id: str) -> list[dict]:
    """Verify numbers in section 4 JSON match source data texts.

    Extracts all numeric values from source data texts and from paper section 4,
    then checks that every number in the paper can be traced to source data.
    Also detects placeholder variables (x1, x2, etc.) when real data exists.

    Returns list of warnings: [{\"path\": \"section4b.text\", \"found\": \"94.5%\", \"source_sample\": [...], \"severity\": \"error\"}]
    Empty list = integrity check passed.
    """
    import re

    warnings = []

    # First: check for placeholder variables when data exists
    if data_texts:
        _PLACEHOLDER_RE = re.compile(
            r'\b(x\d+|X\d+|X₁|X₂|X₃|X₄|X₅|X₆|X₇|X₈|X₉|X₁₀'
            r'|a\d+|a₁|a₂|a₃|a₄|a₅|b\d+|b₁|b₂|b₃|b₄|b₅'
            r'|variabel\s+X|nilai\s+X|placeholder)\b',
            re.IGNORECASE
        )

        def _scan_for_placeholders(obj, path="paper"):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k.startswith("_") or k in ("Prompt", "data_tools_payload"):
                        continue
                    new_path = f"{path}.{k}"
                    if isinstance(v, str):
                        matches = _PLACEHOLDER_RE.findall(v)
                        for m in matches:
                            warnings.append({
                                "path": new_path,
                                "found": m,
                                "issue": "PLACEHOLDER_VARIABLE_WITH_DATA",
                                "severity": "error",
                                "detail": f"Placeholder '{m}' found but ## DATA SUMBER exists. Replace with actual data values."
                            })
                    elif isinstance(v, (dict, list)):
                        _scan_for_placeholders(v, new_path)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    _scan_for_placeholders(item, f"{path}[{i}]")

        _scan_for_placeholders(paper_data)

    # Second: extract all numbers from source data for cross-reference
    source_numbers: set[str] = set()
    source_decimals: set[float] = set()
    if data_texts:
        for dt in data_texts:
            if not dt:
                continue
            clean_dt = re.sub(r'[|*_#`]', ' ', dt)
            for m in re.finditer(r'(\d+[.,]\d+|\d+)(\s*[%]?|\s*\w+)?', clean_dt):
                num_str = m.group(1).replace(',', '.')
                try:
                    num = float(num_str)
                    source_decimals.add(num)
                    source_numbers.add(m.group(0).strip())
                except ValueError:
                    pass

    # Walk section 4 content looking for numeric claims
    def walk_paper(obj, path="paper"):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.startswith("_") or k in ("Prompt", "ImagePath", "TablePrefix"):
                    continue
                new_path = f"{path}.{k}"
                if isinstance(v, str) and ("section4" in path.lower() or
                                           any(hint in new_path.lower() for hint in ["result", "discuss", "findings", "analys"])):
                    # Extract numbers from text
                    paper_text = str(v)
                    for m in re.finditer(r'(\d+[.,]\d+|\d+)(\s*[%]?|\s*\w+)?', paper_text):
                        num_match = m.group(0).strip()
                        # Skip years, equation numbers, citation numbers
                        if re.match(r'^\d{4}$', num_match) and 'year' not in new_path.lower():
                            continue
                        num_str = m.group(1).replace(',', '.')
                        try:
                            num = float(num_str)
                            # Check if this number exists in source (allow tolerance for rounding)
                            found = False
                            for sd in source_decimals:
                                if abs(num - sd) < 1e-6 or abs(round(num) - round(sd)) < 1e-6:
                                    found = True
                                    break
                            if not found:
                                warnings.append({
                                    "path": new_path,
                                    "found": num_match,
                                    "source_sample": list(source_numbers)[:20],
                                    "severity": "error" if abs(num) > 0.01 else "warning"
                                })
                        except ValueError:
                            pass
                elif isinstance(v, (dict, list)):
                    walk_paper(v, new_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                walk_paper(item, f"{path}[{i}]")

    walk_paper(paper_data)
    return warnings


def _reconcile_section_images(paper_data: dict, paper_id: str, upload_base: Path) -> None:
    """Walk sections and update gambar item Path fields to actual generated images.

    The reconcile_figure_images() function only handles the top-level figures list.
    This function handles gambar items embedded directly in sections (section1.content, etc.)
    which is where the LLM actually puts them.

    Matching strategy (in priority order):
    0. ImageGenJob.target_path semantic match (PRIMARY) — match Title/Caption tokens
       against canonical target_path from ImageGenJob table; pick newest mtime for retries.
    1. Filename contains the gambar's ImageNumber (e.g., "fig1_architecture.jpg" → ImageNumber=1)
    2. Filename matches the gambar's original Path base (e.g., "fig1.png" → "fig1_architecture.jpg")
    3. Fallback: oldest unused image by mtime

    Modifies paper_data in place.
    """
    if not isinstance(paper_data, dict):
        return

    # Find all generated images for this paper (check primary user storage first, then legacy)
    try:
        from tools.editor.utils import safe_paper_image_dir
        primary_dir = safe_paper_image_dir(paper_id)
        if primary_dir and primary_dir.exists():
            paper_upload_dir = primary_dir
        else:
            paper_upload_dir = upload_base / paper_id
    except ImportError:
        paper_upload_dir = upload_base / paper_id
    if not paper_upload_dir.exists():
        log.debug("[reconcile_sections] No upload folder for paper %s", paper_id)
        return

    image_files = []
    for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        image_files.extend(paper_upload_dir.glob(f'*{ext}'))

    if not image_files:
        log.debug("[reconcile_sections] No images found for paper %s", paper_id)
        return

    # Sort by mtime as fallback
    image_files.sort(key=lambda f: f.stat().st_mtime)
    log.info("[reconcile_sections] Found %d images for paper %s", len(image_files), paper_id)

    # ── Strategy 0: Build target_path index from ImageGenJob (canonical source of truth) ───
    target_to_newest: dict[str, Path] = {}
    # Track per-target: has_success, failed_count
    target_status: dict[str, dict] = {}  # stem -> {'has_success': bool, 'failed_count': int}
    try:
        from utils.database.models import ImageGenJob, db
        img_jobs = ImageGenJob.query.filter_by(paper_id=paper_id).all()
        for job in img_jobs:
            target = str(job.target_path or "").strip()
            if not target:
                continue
            target_stem = Path(target).stem.lower()
            if target_stem not in target_status:
                target_status[target_stem] = {'has_success': False, 'failed_count': 0}
            if job.status in ("error", "failed"):
                target_status[target_stem]['failed_count'] += 1
            else:
                target_status[target_stem]['has_success'] = True

        # Now build target_to_newest only for targets that have at least one success
        for target_stem, status in target_status.items():
            if not status['has_success']:
                # All jobs for this target failed - skip
                log.debug("[reconcile_sections] target_path %s skipped: all %d jobs failed",
                         target_stem, status['failed_count'])
                continue
            # Find newest file for this target stem (exact or with _N suffix)
            candidates = [f for f in image_files if f.stem.lower() == target_stem or f.stem.lower().startswith(target_stem + "_")]
            if candidates:
                newest = max(candidates, key=lambda f: f.stat().st_mtime)
                target_to_newest[target_stem] = newest
                log.debug("[reconcile_sections] target_path %s -> %s (mtime=%s)",
                         target_stem, newest.name, newest.stat().st_mtime)
    except Exception as e:
        log.warning("[reconcile_sections] ImageGenJob query failed: %s", e)

    # Build filename index for fast matching
    filename_index = {f.name.lower(): f for f in image_files}
    # Also index by stem (filename without extension)
    stem_index = {f.stem.lower(): f for f in image_files}

    # Track which images have been used
    used_images: set[str] = set()

    # Also check top-level figures list to avoid double-mapping
    top_level_figures = paper_data.get("figures", [])
    for fig in top_level_figures:
        if isinstance(fig, dict):
            p = str(fig.get("Path") or fig.get("path") or "")
            if p and os.path.isabs(p) and os.path.exists(p):
                used_images.add(os.path.basename(p).lower())

    def _extract_img_number(item: dict) -> int | None:
        """Extract image number from ImageNumber field or Path."""
        num = item.get("ImageNumber") or item.get("imageNumber")
        if num:
            try:
                return int(str(num).strip())
            except (ValueError, TypeError):
                pass
        # Try path: "gambar/fig1.png" -> 1
        path = str(item.get("Path") or item.get("path") or "")
        import re as _re
        m = _re.search(r'fig(\d+)', path.lower())
        if m:
            return int(m.group(1))
        return None

    def _find_matching_image(item: dict) -> Path | None:
        """Find the best matching image file for a gambar item."""
        img_num = _extract_img_number(item)
        orig_path = str(item.get("Path") or item.get("path") or "")
        item_title = str(item.get("Title") or item.get("Caption") or item.get("title") or "").lower()
        item_caption = str(item.get("Caption") or item.get("caption") or "").lower()
        item_tokens = set((item_title + " " + item_caption).split())

        # Strategy 0 (PRIMARY): Semantic match via ImageGenJob.target_path
        # Score Title+Caption tokens against each target_path stem; best score ≥ 1 wins
        if target_to_newest and item_tokens:
            best_stem: str | None = None
            best_score = 0
            for stem, img_file in target_to_newest.items():
                if img_file.name in used_images:
                    continue
                score = sum(1 for tok in item_tokens if tok in stem or stem in tok)
                if score > best_score:
                    best_score = score
                    best_stem = stem
            if best_stem and best_score >= 1:
                return target_to_newest[best_stem]

        # Strategy 1: Match by ImageNumber in filename (e.g., "fig1_architecture.jpg" for ImageNumber=1)
        if img_num:
            for img_file in image_files:
                if img_file.name in used_images:
                    continue
                # Check if filename starts with "fig{num}_" or is exactly "fig{num}.jpg"
                fname_lower = img_file.stem.lower()
                if fname_lower == f"fig{img_num}" or fname_lower.startswith(f"fig{img_num}_"):
                    return img_file

        # Strategy 2: Match by original Path base name
        if orig_path:
            import os as _os
            orig_base = _os.path.splitext(_os.path.basename(orig_path))[0].lower()
            # Normalise: remove stray spaces that AI models insert mid-token
            # (e.g. "system_a rchitecture" → "system_architecture")
            orig_base_norm = orig_base.replace(" ", "") if orig_base else ""
            if orig_base and orig_base != "image":
                # Check exact stem match
                if orig_base in stem_index:
                    candidate = stem_index[orig_base]
                    if candidate.name not in used_images:
                        return candidate
                # Check normalised stem match (spaces removed from both sides)
                if orig_base_norm and orig_base_norm != orig_base:
                    for stem, img_file in stem_index.items():
                        if stem.replace(" ", "") == orig_base_norm and img_file.name not in used_images:
                            return img_file
                # Check prefix match (e.g., "fig1" matches "fig1_architecture")
                for stem, img_file in stem_index.items():
                    if stem.startswith(orig_base) and img_file.name not in used_images:
                        return img_file
                    # Also try normalised prefix match
                    if orig_base_norm and stem.replace(" ", "").startswith(orig_base_norm) and img_file.name not in used_images:
                        return img_file

        # Strategy 3: Match by ImageNumber position (legacy fallback)
        if img_num and img_num <= len(image_files):
            candidate = image_files[img_num - 1]
            if candidate.name not in used_images:
                return candidate

        # Strategy 4: Use next available unused image (oldest first)
        for img in image_files:
            if img.name not in used_images:
                return img

        return None

    def walk_sections(obj):
        if isinstance(obj, dict):
            if obj.get("id") == "gambar":
                current_path = str(obj.get("Path") or obj.get("path") or "").strip()
                # Skip if already has absolute path to existing file
                if current_path and os.path.isabs(current_path) and os.path.exists(current_path):
                    return
                # Find matching image
                matched = _find_matching_image(obj)
                if matched:
                    obj["Path"] = str(matched)
                    used_images.add(matched.name)
                    log.debug("[reconcile_sections] Mapped gambar to %s", matched.name)
            # Recurse into all dict values
            for v in obj.values():
                walk_sections(v)
        elif isinstance(obj, list):
            for item in obj:
                walk_sections(item)

    walk_sections(paper_data)
    log.info("[reconcile_sections] Mapped %d/%d images for paper %s", len(used_images), len(image_files), paper_id)

def _run_section4_chart_render(
    app, job_id: str, paper_id: str, user_id: int,
    chart_specs: list[dict], combined_data: str
):
    """Background worker: Generate matplotlib charts from section 4 specs.

    Each spec may contain:
    - data_tools_payload: structured JSON chart spec (from LLM) → use chart_generator directly
    - Prompt: text with chart type + markdown table data → use legacy _render_matplotlib_chart
    - source_tables: section 4 table data → use chart_generator with section 4 data

    Falls back to VIOLA-CHAT (via format_data_with_ai) when no structured data is available.
    """
    import logging
    logger = logging.getLogger(__name__)

    with app.app_context():
        from utils.database.models import AiJob, PaperImage, Paper, db, safe_commit
        from tools.editor.utils import safe_paper_image_dir
        from pathlib import Path
        import re

        job = AiJob.query.get(job_id)
        if not job:
            return

        def _save_paper_image_record(chart_path: str, title: str, idx: int, img_num: str):
            """Save PaperImage DB record for a generated chart."""
            if not chart_path or not paper:
                return
            try:
                safe_num = re.sub(r'[^0-9]', '', str(img_num)) or str(idx + 1)
                chart_filename = Path(chart_path).name
                img_record = PaperImage(
                    paper_id=paper_id,
                    user_id=user_id,
                    filename=chart_filename,
                    original_name=title or f"Chart {safe_num}",
                    file_path=f"{paper_id}/{chart_filename}",
                )
                db.session.add(img_record)
                safe_commit()
                logger.info("[sec4_charts] Saved PaperImage record for %s", chart_filename)
            except Exception as e_img:
                logger.warning("[sec4_charts] Failed to save image record: %s", e_img)
                db.session.rollback()

        def _render_from_payload(payload: dict, idx: int, img_num: str, target_path: str = None) -> str | None:
            """Render chart directly from data_tools_payload via chart_generator."""
            try:
                from tools.data.auto_data_tools import _payload_to_chart_spec, _generate_chart_from_spec
                spec_dict = _payload_to_chart_spec(payload, paper_id)
                if not spec_dict:
                    logger.warning("[sec4_charts] _payload_to_chart_spec returned None for spec %d", idx)
                    return None
                chart_title = payload.get("title") or title or f"Chart {img_num}"
                result = _generate_chart_from_spec(
                    spec_dict, user_id, paper_id, chart_title,
                    target_path=target_path,
                )
                if result:
                    return result.get("path")
            except Exception as e:
                logger.warning("[sec4_charts] _render_from_payload failed for spec %d: %s", idx, e)
            return None

        def _render_from_tables(tables: list[dict], idx: int, img_num: str, chart_kind: str = "bar", target_path: str = None) -> str | None:
            """Render chart from section 4 table data via chart_generator."""
            if not tables:
                return None
            try:
                from tools.data.chart_generator import ChartSpec, generate_chart
                import shutil

                tbl = tables[0]
                cols = tbl.get("columns") or tbl.get("headers") or []
                rows = tbl.get("rows") or tbl.get("data") or []
                if not cols or not rows:
                    return None

                # First column is categories, rest are series
                categories = [str(r[0]) if isinstance(r, list) and r else str(r) for r in rows]
                data_rows = []
                for col_idx in range(1, len(cols)):
                    series = []
                    for r in rows:
                        if isinstance(r, list) and col_idx < len(r):
                            v = str(r[col_idx]).replace("%", "").replace(",", "").strip()
                            try:
                                series.append(float(v))
                            except (ValueError, TypeError):
                                series.append(0.0)
                        else:
                            series.append(0.0)
                    data_rows.append(series)

                if not data_rows:
                    return None

                spec = ChartSpec(
                    kind=chart_kind,
                    title=title or f"Chart {img_num}",
                    xlabel=cols[0] if cols else "",
                    ylabel=cols[1] if len(cols) > 1 else "",
                    data=data_rows,
                    series_labels=cols[1:] if len(cols) > 1 else ["Value"],
                    x_data=categories,
                    color_palette="academic",
                    theme="clean",
                )

                safe_num = re.sub(r'[^0-9]', '', str(img_num)) or str(idx + 1)
                out_path = Path(generate_chart(paper_id, spec, user_id=user_id, judul_paper=title, target_path=target_path))
                # Move to paper image directory
                if paper_dir:
                    dest = paper_dir / out_path.name
                    shutil.move(str(out_path), str(dest))
                    return str(dest)
                return str(out_path)
            except Exception as e:
                logger.warning("[sec4_charts] _render_from_tables failed for spec %d: %s", idx, e)
            return None

        try:
            job.status = "running"
            job.stage = "generating_charts"
            job.progress = 10
            safe_commit()

            paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
            paper_dir = safe_paper_image_dir(paper_id)
            if paper_dir:
                paper_dir.mkdir(parents=True, exist_ok=True)

            created_charts = []
            for idx, spec in enumerate(chart_specs):
                chart_path = None
                try:
                    prompt = spec.get("Prompt", "")
                    title = spec.get("Title", "")
                    img_num = spec.get("ImageNumber", str(idx + 1))
                    # Extract target_path from paper JSON Path (e.g., 'gambar/fig4_1_settling_time.png')
                    target_path = spec.get("Path", "") or spec.get("path", "")

                    # ── PATH 1: data_tools_payload present → use chart_generator directly ──
                    payload = spec.get("data_tools_payload")
                    if payload and isinstance(payload, dict):
                        logger.info("[sec4_charts] Spec %d: using data_tools_payload (kind=%s)",
                                   idx, payload.get("kind", "?"))
                        chart_path = _render_from_payload(payload, idx, img_num, target_path=target_path)

                    # ── PATH 2: source_tables present → render from section 4 table data ──
                    if not chart_path:
                        source_tables = spec.get("source_tables", [])
                        if source_tables:
                            # Parse chart kind from prompt
                            chart_kind = "bar"
                            type_match = re.search(
                                r'(bar|line|scatter|pie|stacked_bar|heatmap|area)\s*(chart|plot|graph)?',
                                prompt, re.IGNORECASE
                            )
                            if type_match:
                                chart_kind = type_match.group(1).lower()
                            logger.info("[sec4_charts] Spec %d: using source_tables (%d tables, kind=%s)",
                                       idx, len(source_tables), chart_kind)
                            chart_path = _render_from_tables(source_tables, idx, img_num, chart_kind, target_path=target_path)

                    # ── PATH 3: Parse markdown table from Prompt text ──
                    if not chart_path and prompt:
                        chart_type = "bar"
                        type_match = re.search(
                            r'(bar|line|scatter|pie|stacked_bar|heatmap|area)\s*(chart|plot|graph)?',
                            prompt, re.IGNORECASE
                        )
                        if type_match:
                            chart_type = type_match.group(1).lower()

                        data_table = _extract_data_from_spec(prompt)
                        if not data_table and combined_data:
                            logger.warning("[sec4_charts] Spec %d: no data in prompt, trying combined_data", idx)
                            data_table = _extract_data_from_spec(combined_data)

                        if data_table:
                            logger.info("[sec4_charts] Spec %d: using legacy markdown parse", idx)
                            chart_info = _render_matplotlib_chart(
                                chart_type=chart_type,
                                data_table=data_table,
                                title=title or _extract_title_from_prompt(prompt),
                                prompt=prompt,
                                paper_id=paper_id,
                                paper_dir=paper_dir,
                                img_num=img_num,
                            )
                            if chart_info:
                                chart_path = chart_info.get("path")

                    # ── PATH 4: VIOLA-CHAT fallback — analyze combined_data ──
                    if not chart_path and combined_data:
                        try:
                            logger.info("[sec4_charts] Spec %d: VIOLA-CHAT fallback for data analysis", idx)
                            from tools.data.dataFormating import format_data_with_ai
                            result = format_data_with_ai(
                                f"### Instruksi: Data untuk grafik section 4 paper akademik\n"
                                f"### Gambar: {title or prompt[:80]}\n\n{combined_data}",
                                filename=title or f"chart_{img_num}",
                            )
                            tables = result.get("tables", [])
                            recs = result.get("chart_recommendations", [])
                            if tables and recs:
                                rec = recs[0]
                                chart_kind = rec.get("kind", "bar")
                                logger.info("[sec4_charts] Spec %d: VIOLA-CHAT returned %d tables, %d recs (kind=%s)",
                                           idx, len(tables), len(recs), chart_kind)
                                chart_path = _render_from_tables(tables, idx, img_num, chart_kind)
                        except Exception as e_ai:
                            logger.warning("[sec4_charts] Spec %d: VIOLA-CHAT fallback failed: %s", idx, e_ai)

                    if chart_path:
                        chart_filename = Path(chart_path).name
                        created_charts.append({
                            "path": chart_path,
                            "filename": chart_filename,
                            "title": title or f"Chart {img_num}",
                        })
                        _save_paper_image_record(chart_path, title, idx, img_num)
                        # Simpan ke user storage (user/<username>/<paper_id>/image/)
                        try:
                            from utils.core.user_storage import get_username, get_paper_base_by_id, _ensure_dir
                            import shutil as _shutil
                            username = get_username(user_id=user_id)
                            base = get_paper_base_by_id(username, paper_id)
                            img_dir = _ensure_dir(base / "image")
                            dest = img_dir / chart_filename
                            _shutil.copy2(str(chart_path), str(dest))
                        except Exception:
                            logger.warning("[sec4_charts] Gagal simpan chart ke user storage", exc_info=True)
                    else:
                        logger.warning("[sec4_charts] Spec %d: all render paths failed, skipping", idx)

                    progress = 10 + int(80 * (idx + 1) / len(chart_specs))
                    job.progress = progress
                    job.stage = f"generating ({idx+1}/{len(chart_specs)})"
                    safe_commit()

                except Exception as e_spec:
                    logger.warning("[sec4_charts] Chart %d failed: %s", idx, e_spec)

            # Finalize
            job.status = "done"
            job.stage = "complete"
            job.progress = 100
            job.finished_at = datetime.now(timezone.utc)
            job.result = {
                "specs_count": len(chart_specs),
                "charts_count": len(created_charts),
                "charts": created_charts,
                "source": "section4_specs",
            }
            safe_commit()
            logger.info("[sec4_charts] Generated %d/%d charts for paper %s",
                       len(created_charts), len(chart_specs), paper_id)

        except Exception as e:
            logger.exception("[sec4_charts] Failed for paper %s: %s", paper_id, e)
            try:
                job.status = "error"
                job.error = str(e)[:2000]
                safe_commit()
            except Exception:
                pass
        finally:
            # Worker-level guard: daemon thread can die silently on gunicorn restart.
            # If job is still 'running' after all normal paths, mark as error.
            # Re-fetch to avoid stale object issues.
            try:
                _final_job = AiJob.query.get(job_id)
                if _final_job and _final_job.status == "running":
                    _final_job.status = "error"
                    _final_job.error = "Worker thread terminated unexpectedly (server restart or daemon death)"
                    _final_job.finished_at = datetime.now(timezone.utc)
                    safe_commit()
                    logger.warning("[sec4_charts] Daemon guard: marked job %s as error (thread died)", job_id)
            except Exception:
                pass


def _extract_data_from_spec(prompt: str) -> list[dict] | None:
    """Extract data table from a chart specification prompt.

    Supports:
    - Markdown table format: | Col1 | Col2 | \\n| val1 | val2 |
    - Key-value pairs: {Key: Val, Key2: Val2}
    - CSV-like: Col1,Col2\\nval1,val2

    Returns list of row dicts, or None if no data found.
    """
    import re

    # Try markdown table
    lines = prompt.strip().split('\n')
    if len(lines) >= 2:
        header_line = lines[0].strip('|')
        headers = [h.strip() for h in header_line.split('|')]
        if len(headers) >= 2:
            # Skip separator row (contains only dashes), rest = data rows
            data_rows = []
            for line in lines[1:]:
                row_str = line.strip().strip('|')
                if not row_str:
                    continue
                cells = [c.strip() for c in row_str.split('|')]
                # Skip separator rows
                if all(c.replace('-', '').replace(':', '').strip() == '' for c in cells):
                    continue
                if len(cells) == len(headers):
                    data_rows.append(dict(zip(headers, cells)))
                elif len(cells) > 0:
                    # Pad or trim
                    padded = cells[:len(headers)]
                    while len(padded) < len(headers):
                        padded.append("")
                    data_rows.append(dict(zip(headers, padded)))
            if data_rows:
                return data_rows

    # Legacy fallback: regex-based parsing
    md_pattern = re.findall(r'\|(.+?)\|', prompt)
    if len(md_pattern) >= 3:
        # First row = headers, rest = data rows
        headers = [h.strip() for h in md_pattern[0].split('|')]
        # Skip separator row (contains only dashes)
        data_rows = []
        for row_str in md_pattern[1:]:
            cells = [c.strip() for c in row_str.split('|')]
            # Skip separator rows
            if all(c.replace('-', '').replace(':', '').strip() == '' for c in cells):
                continue
            if len(cells) == len(headers):
                data_rows.append(dict(zip(headers, cells)))
            elif len(cells) > 0:
                # Pad or trim
                padded = cells[:len(headers)]
                while len(padded) < len(headers):
                    padded.append('')
                data_rows.append(dict(zip(headers, padded)))
        if data_rows:
            return data_rows

    # Try {Key: Val, ...} format
    kv_pattern = re.findall(r'\{([^}]+)\}', prompt)
    if kv_pattern:
        rows = []
        for kv_str in kv_pattern:
            pairs = re.findall(r'(\w+[\s\w]*)\s*:\s*([^,}]+)', kv_str)
            if pairs:
                rows.append({k.strip(): v.strip() for k, v in pairs})
        if rows:
            return rows

    return None


def _extract_title_from_prompt(prompt: str) -> str:
    """Extract a chart title from the prompt text."""
    import re
    # Look for "Title: ..." pattern
    m = re.search(r'[Tt]itle:\s*([^.\n]+)', prompt)
    if m:
        return m.group(1).strip()
    # Fallback: first few words
    words = prompt.split()[:8]
    return ' '.join(words)[:60]


def _render_matplotlib_chart(
    chart_type: str,
    data_table: list[dict],
    title: str,
    prompt: str,
    paper_id: str,
    paper_dir,
    img_num: str,
) -> dict | None:
    """Render a matplotlib chart from parsed data.

    Returns dict with 'path', 'type', 'title' or None on failure.
    """
    import logging
    import re
    logger = logging.getLogger(__name__)

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
        from pathlib import Path

        if not data_table:
            return None

        # Determine output path
        safe_num = re.sub(r'[^0-9]', '', img_num) or '1'
        # Use fig{num}_chart.png so reconcile can match by ImageNumber
        filename = f"fig{safe_num}_chart.png"
        if paper_dir:
            out_path = paper_dir / filename
        else:
            out_path = Path(f"/tmp/fig{safe_num}_chart_{paper_id}.png")

        # Extract numeric columns
        if not data_table or len(data_table) == 0:
            return None
        headers = list(data_table[0].keys())
        if not headers:
            logger.warning("[matplot] No headers found in data table")
            return None
        # Find numeric columns
        num_cols = []
        cat_col = headers[0] if headers else f"Item"  # Assume first column is category
        for h in headers[1:]:
            try:
                vals = []
                for row in data_table:
                    v = str(row.get(h, '')).replace('%', '').replace(',', '').strip()
                    float(v)
                    vals.append(float(v))
                if vals:
                    num_cols.append((h, vals))
            except (ValueError, TypeError):
                pass

        if not num_cols:
            logger.warning("[matplot] No numeric columns found")
            return None

        categories = [str(row.get(cat_col, f'Item {i+1}')) for i, row in enumerate(data_table)]

        # Extract axis labels from prompt
        x_label = ""
        y_label = ""
        m_x = re.search(r'[Xx]-axis:\s*"([^"\n]+)', prompt)
        m_y = re.search(r'[Yy]-axis:\s*"([^"\n]+)', prompt)
        if m_x:
            x_label = m_x.group(1).strip()
        if m_y:
            y_label = m_y.group(1).strip()

        # Create chart
        fig, ax = plt.subplots(figsize=(10, 6))
        x = np.arange(len(categories))
        width = 0.8 / max(len(num_cols), 1)

        if chart_type == 'bar':
            for i, (col_name, vals) in enumerate(num_cols):
                offset = (i - len(num_cols)/2 + 0.5) * width
                ax.bar(x + offset, vals, width, label=col_name)
            ax.set_xticks(x)
            ax.set_xticklabels(categories, rotation=30, ha='right', fontsize=9)

        elif chart_type == 'line':
            for col_name, vals in num_cols:
                ax.plot(x, vals, marker='o', linewidth=2, label=col_name)
            ax.set_xticks(x)
            ax.set_xticklabels(categories, rotation=30, ha='right', fontsize=9)

        elif chart_type == 'scatter':
            if len(num_cols) >= 2:
                ax.scatter(num_cols[0][1], num_cols[1][1], s=60, alpha=0.7)
                ax.set_xlabel(num_cols[0][0])
                ax.set_ylabel(num_cols[1][0])
            elif len(num_cols) == 1:
                ax.scatter(x, num_cols[0][1], s=60, alpha=0.7)
            else:
                logger.warning("[matplot] scatter requires at least 1 numeric column, got %d", len(num_cols))
                plt.close(fig)
                return None

        elif chart_type == 'pie':
            if len(num_cols) >= 1:
                vals = num_cols[0][1]
                ax.pie(vals, labels=categories, autopct='%1.1f%%', startangle=90)
                ax.axis('equal')
            else:
                logger.warning("[matplot] pie requires at least 1 numeric column, got %d", len(num_cols))
                plt.close(fig)
                return None

        elif chart_type == 'stacked_bar':
            if not num_cols:
                logger.warning("[matplot] stacked_bar requires numeric columns")
                plt.close(fig)
                return None
            bottoms = np.zeros(len(categories))
            for col_name, vals in num_cols:
                ax.bar(x, vals, width*len(num_cols), bottom=bottoms, label=col_name)
                bottoms += np.array(vals)
            ax.set_xticks(x)
            ax.set_xticklabels(categories, rotation=30, ha='right', fontsize=9)

        elif chart_type == 'heatmap':
            if len(num_cols) >= 2:
                data_matrix = [v for _, v in num_cols]
                im = ax.imshow(data_matrix, aspect='auto', cmap='YlOrRd')
                ax.set_xticks(range(len(categories)))
                ax.set_xticklabels(categories, rotation=30, ha='right', fontsize=9)
                ax.set_yticks(range(len(num_cols)))
                ax.set_yticklabels([n for n, _ in num_cols])
                plt.colorbar(im, ax=ax, shrink=0.8)
            else:
                logger.warning("[matplot] heatmap requires at least 2 numeric columns, got %d", len(num_cols))
                plt.close(fig)
                return None

        else:  # area or fallback
            if not num_cols:
                logger.warning("[matplot] area chart requires numeric columns")
                plt.close(fig)
                return None
            for col_name, vals in num_cols:
                ax.fill_between(x, vals, alpha=0.3, label=col_name)
                ax.plot(x, vals, linewidth=1.5)
            ax.set_xticks(x)
            ax.set_xticklabels(categories, rotation=30, ha='right', fontsize=9)

        ax.set_title(title, fontsize=13, fontweight='bold', pad=15)
        if x_label and chart_type != 'scatter':
            ax.set_xlabel(x_label)
        if y_label and chart_type not in ('scatter', 'pie'):
            ax.set_ylabel(y_label)
        if len(num_cols) > 1 and chart_type != 'pie':
            ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(str(out_path), dpi=150, bbox_inches='tight')
        plt.close(fig)

        logger.info("[matplot] Saved chart %s → %s", chart_type, out_path)
        return {"path": str(out_path), "type": chart_type, "title": title}

    except Exception as e:
        logger.exception("[matplot] Chart render failed: %s", e)
        return None


def _run_data_chart_render(app, job_id: str, paper_id: str, user_id: int, combined: str):
    """Background worker: AI analyze data → generate matplotlib charts.
    
    Processes data PER FILE to ensure minimum 2 tables + 2 charts per Excel.
    """
    import logging
    logger = logging.getLogger(__name__)

    with app.app_context():
        from utils.database.models import AiJob, PaperImage, Paper, db, safe_commit
        from tools.editor.utils import safe_paper_image_dir
        from pathlib import Path

        job = AiJob.query.get(job_id)
        if not job:
            return

        try:
            # ── Step 1: AI formatting (per-file) ─────────────────────
            job.status = "running"
            job.stage = "ai_formatting"
            job.progress = 25
            safe_commit()

            from tools.data.dataFormating import format_data_with_ai

            # Split combined data by file markers for per-file processing
            # _extract_texts_from_files outputs "=== Extracted from: filename ===" headers
            import re
            file_sections = re.split(r'\n=== Extracted from: (.+?) ===\n', combined)
            
            all_tables = []
            all_recs = []
            
            if len(file_sections) > 1:
                # Multiple files detected — process each separately
                # file_sections[0] is before first marker (usually empty)
                # file_sections[1] is filename1, [2] is content1, [3] is filename2, etc.
                file_pairs = []
                i = 1
                while i < len(file_sections) - 1:
                    fname = file_sections[i].strip()
                    content = file_sections[i + 1] if i + 1 < len(file_sections) else ""
                    if content.strip():
                        file_pairs.append((fname, content))
                    i += 2
                
                logger.info("[auto_chart] Processing %d files separately for paper %s",
                           len(file_pairs), paper_id)
                
                for idx, (fname, content) in enumerate(file_pairs):
                    progress = 25 + int(30 * (idx + 1) / len(file_pairs))
                    job.progress = progress
                    job.stage = f"ai_formatting ({idx+1}/{len(file_pairs)}: {fname})"
                    safe_commit()
                    
                    result = format_data_with_ai(
                        f"### Instruksi: Data untuk grafik section 4 paper akademik\n"
                        f"### File: {fname}\n\n{content}",
                        filename=fname
                    )
                    tables = result.get("tables", [])
                    recs = result.get("chart_recommendations", [])
                    
                    # Enforce minimum 2 tables + 2 charts per file
                    if len(tables) < 2:
                        logger.warning("[auto_chart] File %s only produced %d tables, "
                                     "minimum 2 required", fname, len(tables))
                    if len(recs) < 2:
                        logger.warning("[auto_chart] File %s only produced %d chart recs, "
                                     "minimum 2 required", fname, len(recs))
                    
                    all_tables.extend(tables)
                    all_recs.extend(recs)
                    logger.info("[auto_chart] File %s → %d tables, %d charts",
                              fname, len(tables), len(recs))
            else:
                # Single file or no file markers — process as one
                result = format_data_with_ai(
                    f"### Instruksi: Data untuk grafik section 4 paper akademik\n\n{combined}"
                )
                all_tables = result.get("tables", [])
                all_recs = result.get("chart_recommendations", [])

            if not all_tables:
                logger.warning("[auto_chart] No tables extracted for paper %s", paper_id)
                job.status = "done"
                job.stage = "complete"
                job.progress = 100
                job.finished_at = datetime.now(timezone.utc)
                safe_commit()
                return

            logger.info("[auto_chart] Total extracted %d tables, %d chart recs for paper %s",
                       len(all_tables), len(all_recs), paper_id)

            # ── Step 2: Generate charts ─────────────────────────────
            job.stage = "generating_charts"
            job.progress = 55
            safe_commit()

            paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
            paper_dir = safe_paper_image_dir(paper_id)
            if paper_dir:
                paper_dir.mkdir(parents=True, exist_ok=True)

            created_charts = []
            for i, rec in enumerate(all_recs):
                try:
                    from tools.data.data_worker import _generate_chart_from_rec
                    chart_info = _generate_chart_from_rec(
                        rec, all_tables, paper_id, user_id, paper, paper_dir
                    )
                    if chart_info:
                        created_charts.append(chart_info)
                except Exception as e:
                    logger.warning("[auto_chart] Chart %d failed: %s", i, e)

            # ── Step 3: Finalize ───────────────────────────────────
            job.status = "done"
            job.stage = "complete"
            job.progress = 100
            job.finished_at = datetime.now(timezone.utc)
            job.result = {
                "tables_count": len(all_tables),
                "charts_count": len(created_charts),
                "charts": created_charts,
                "source": "auto_data_chart",
            }
            safe_commit()
            logger.info("[auto_chart] Generated %d charts for paper %s", len(created_charts), paper_id)

        except Exception as e:
            logger.exception("[auto_chart] Failed for paper %s: %s", paper_id, e)
            try:
                job.status = "error"
                job.stage = "error"
                job.progress = 0
                safe_commit()
            except Exception:
                pass
        finally:
            # Worker-level guard: daemon thread can die silently on gunicorn restart.
            try:
                _final_job = AiJob.query.get(job_id)
                if _final_job and _final_job.status == "running":
                    _final_job.status = "error"
                    _final_job.error = "Worker thread terminated unexpectedly (server restart or daemon death)"
                    _final_job.finished_at = datetime.now(timezone.utc)
                    safe_commit()
            except Exception:
                pass


# Single Redis connection reused across requests/workers.
_REDIS = None
_REDIS_LOCK = threading.Lock()


def get_redis():
    global _REDIS
    if _REDIS is None:
        with _REDIS_LOCK:
            if _REDIS is None:
                try:
                    _REDIS = redis.Redis.from_url(
                        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
                        decode_responses=True,
                    )
                except Exception:
                    return None
    return _REDIS


def progress_channel(job_id: str) -> str:
    return f"job:{job_id}:progress"


def cancel_key(job_id: str) -> str:
    return f"job:{job_id}:cancel"


def publish_progress(job_id: str, payload: dict) -> None:
    """Worker calls this to push progress events. UI subscribes via SSE."""
    try:
        _r = get_redis()
        if _r:
            _r.publish(progress_channel(job_id), json.dumps(payload, default=str))
            # Keep last snapshot for late subscribers (24h TTL).
            _r.setex(f"job:{job_id}:last", 86400, json.dumps(payload, default=str))
    except Exception:
        pass


# ── Endpoints ───────────────────────────────────────────────────────────────


@jobs.route("/api/papers/<paper_id>/generate", methods=["POST"])
@jwt_required()
def enqueue_generate(paper_id: str):
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    # Validate paper_id format to prevent path traversal
    if not re.match(r"^[A-Za-z0-9_-]{1,64}$", paper_id):
        return jsonify({"error": "Invalid paper id"}), 400

    # ── Quota gate ────────────────────────────────────────────────────────
    from utils.quota import quota_exceeded
    exceeded, info = quota_exceeded(user_id)
    if exceeded:
        return jsonify(info), 429

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "paper not found"}), 404

    # Check if there's already an active job for this paper (prevent double-generate)
    active_job = AiJob.query.filter_by(
        paper_id=paper_id,
        user_id=user_id
    ).filter(
        AiJob.status.in_(["queued", "running", "pending"])
    ).first()
    if active_job:
        return jsonify({
            "error": "Paper ini sedang dalam proses generate. Tunggu sampai selesai.",
            "existing_job_id": active_job.id,
        }), 409  # Conflict

    # Support both JSON and multipart/form-data
    pdf_texts = []
    if request.content_type and 'multipart/form-data' in request.content_type:
        prompt = (request.form.get("prompt") or "").strip()
        topic = request.form.get("topic") or None
        style = request.form.get("style") or None
        language = request.form.get("language") or None
        include_status = request.form.get("include_status", "true").lower() == "true"
        selected_facts_raw = request.form.get("selected_facts")
        selected_files_raw = request.form.get("selected_files")
        selected_tables_raw = request.form.get("selected_tables")
        selected_drafts_raw = request.form.get("selected_drafts")
        try:
            selected_facts = json.loads(selected_facts_raw) if selected_facts_raw else None
            selected_files = json.loads(selected_files_raw) if selected_files_raw else None
            selected_tables = json.loads(selected_tables_raw) if selected_tables_raw else None
            selected_drafts = json.loads(selected_drafts_raw) if selected_drafts_raw else None
        except (json.JSONDecodeError, TypeError):
            return jsonify({"error": "Invalid JSON in selected_facts/selected_files/selected_tables/selected_drafts"}), 400
        
        # Extract text from uploaded files
        uploaded_files = request.files.getlist("files")
        if uploaded_files:
            from main import _extract_texts_from_files
            pdf_texts = _extract_texts_from_files(uploaded_files)
    else:
        body = request.get_json(silent=True) or {}
        prompt = (body.get("prompt") or "").strip()
        topic = body.get("topic") or None
        style = body.get("style") or None
        language = body.get("language") or None
        include_status = body.get("include_status", True)
        selected_facts = body.get("selected_facts")
        selected_files = body.get("selected_files")
        selected_tables = body.get("selected_tables")
        selected_drafts = body.get("selected_drafts")
        pdf_texts = body.get("pdf_texts") or []
    
    if not prompt:
        return jsonify({"error": "prompt required"}), 400

    # Build custom_prompt dengan status context dari status.json
    custom_prompt = ""
    
    # Append extracted file texts to custom_prompt
    if pdf_texts:
        custom_prompt += "\n\n## Extracted File Contents\n" + "\n".join(pdf_texts)
    
    # Check if user wants to include status.json data
    if include_status:
        try:
            from utils.core.user_storage import build_status_context, get_username
            
            username = get_username(user_id=user_id)
            status_context = build_status_context(
                username, 
                paper_id,
                selected_facts=selected_facts,
                selected_files=selected_files,
                selected_tables=selected_tables
            )
            
            if status_context:
                custom_prompt = (custom_prompt + "\n\n" + status_context).strip()
        except Exception as e:
            log.warning(f"Failed to build status context for paper {paper_id}: {e}")

    # Inject selected chat drafts as additional context
    # selected_drafts can be:
    #   - str: pre-formatted text block (new frontend sends drafts as text directly)
    #   - list: JSON array of draft names (legacy, fetch from DB)
    if selected_drafts:
        if isinstance(selected_drafts, str):
            # Pre-formatted text from frontend (drafts already embedded in referenceFiles)
            draft_block = selected_drafts
        else:
            # Legacy: list of names → fetch from DB
            try:
                from tools.chat.drafts import get_drafts_by_names
                draft_block = get_drafts_by_names(paper_id, user_id, selected_drafts, max_items=10)
            except Exception as e:
                log.warning("Failed to load drafts for paper %s: %s", paper_id, e)
                draft_block = None
        if draft_block:
            custom_prompt = (custom_prompt + "\n\n## Chat Drafts (user-selected context)\n" + draft_block).strip()
            log.info("Injected draft(s) into paperfull job for paper %s", paper_id)

    job_id = uuid.uuid4().hex[:16]
    job = AiJob(
        id=job_id,
        user_id=user_id,
        paper_id=paper_id,
        kind="generate_paper",
        status="queued",
        progress=0,
        stage="queued",
        prompt=prompt[:4000],
    )
    db.session.add(job)
    try:
        safe_commit()
    except Exception:
        db.session.rollback()
        raise

    # Lazy import so this blueprint can be imported even if RQ is missing during
    # cold paths (alembic, tests).
    from rq import Queue

    from tools.paperfull.paper_worker import run_generate_paper

    q = Queue("paper", connection=get_redis())
    q.enqueue(
        run_generate_paper,
        job_id,
        user_id,
        paper_id,
        prompt,
        topic,
        style,
        language,
        custom_prompt=custom_prompt,
        job_timeout=3600,
        result_ttl=3600,
        failure_ttl=86400,
    )
    publish_progress(job_id, {"stage": "queued", "percent": 0})
    return jsonify({"job_id": job_id, "status": "queued"})


@jobs.route("/api/jobs/<job_id>", methods=["GET"])
@jwt_required()
def get_job(job_id: str):
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    job: Optional[AiJob] = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "not found"}), 404
    return jsonify(job.to_dict())


@jobs.route("/api/jobs/<job_id>/cancel", methods=["POST"])
@jwt_required()
def cancel_job(job_id: str):
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    job = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "not found"}), 404
    if job.status in ("done", "error", "cancelled"):
        return jsonify({"ok": True, "status": job.status})
    _r = get_redis()
    if _r:
        _r.setex(cancel_key(job_id), 3600, "1")
    job.status = "cancelled"
    safe_commit()
    publish_progress(job_id, {"stage": "cancelled", "percent": job.progress, "status": "cancelled"})
    return jsonify({"ok": True})


@jobs.route("/api/papers/<paper_id>/active-jobs", methods=["GET"])
@jwt_required()
def active_jobs(paper_id: str):
    """Used by the UI on paper-load to resume any in-flight generation."""
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    rows = (
        AiJob.query.filter_by(user_id=user_id, paper_id=paper_id)
        .filter(AiJob.status.in_(["queued", "running"]))
        .order_by(AiJob.started_at.desc())
        .limit(5)
        .all()
    )
    return jsonify({"jobs": [j.to_dict() for j in rows]})


@jobs.route("/api/jobs/<job_id>/stream", methods=["GET"])
def stream_job(job_id: str):
    """SSE stream. Accepts token via query param or cookie+CSRF.
    Pumps a snapshot first (so late subscribers catch up), then
    pubsub events until the job terminates or the client disconnects."""
    # EventSource doesn't send custom headers — accept token via query param
    # or httpOnly cookie (access_token_cookie). EventSource sends cookies
    # automatically for same-origin requests.
    token = request.args.get('token')
    user_id = None

    if token:
        try:
            from flask_jwt_extended import decode_token
            decoded = decode_token(token)
            user_id = int(decoded['sub'])
        except Exception:
            pass

    # Fallback: read JWT from httpOnly cookie (EventSource sends it automatically)
    if not user_id:
        cookie_token = request.cookies.get('access_token_cookie')
        if cookie_token:
            try:
                from flask_jwt_extended import decode_token
                decoded = decode_token(cookie_token)
                user_id = int(decoded['sub'])
            except Exception:
                pass

    if not user_id:
        try:
            verify_jwt_in_request()
            user_id = int(get_jwt_identity())
        except Exception:
            pass

    if not user_id:
        return jsonify({"error": "Missing authorization token", "code": "UNAUTHORIZED"}), 401
    
    job = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "not found"}), 404

    def gen():
        # Snapshot from DB so reconnect shows current state immediately.
        snap = {
            "stage": job.stage or "queued",
            "percent": int(job.progress or 0),
            "status": job.status,
        }
        yield f"event: snapshot\ndata: {json.dumps(snap)}\n\n"

        # If job already terminal, send done and exit.
        if job.status in ("done", "error", "cancelled"):
            yield f"event: done\ndata: {json.dumps({'status': job.status})}\n\n"
            return

        _r = get_redis()
        if not _r:
            yield ": no redis\n\n"
            return
        pubsub = _r.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(progress_channel(job_id))
        try:
            t0 = time.time()
            last_ping = t0
            while True:
                msg = pubsub.get_message(timeout=1.0)
                if msg and msg.get("type") == "message":
                    data = msg.get("data") or "{}"
                    yield f"event: progress\ndata: {data}\n\n"
                    try:
                        parsed = json.loads(data)
                        if parsed.get("status") in ("done", "error", "cancelled"):
                            yield f"event: done\ndata: {json.dumps({'status': parsed.get('status')})}\n\n"
                            break
                    except Exception:
                        pass
                # Heartbeat every 15s so proxies don't kill the connection.
                if time.time() - last_ping > 15:
                    yield ": ping\n\n"
                    last_ping = time.time()
                # Hard cap 15 min per stream (resubscribe on client side).
                if time.time() - t0 > 900:
                    break
        finally:
            try:
                pubsub.unsubscribe()
                pubsub.close()
            except Exception:
                pass

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return Response(stream_with_context(gen()), headers=headers)


# ── Phase 1c — chunked generate workflow endpoints ──────────────────────────
#
# These endpoints power the chat-side progress bubble and the recent-done
# inbox badge. They live alongside the legacy /api/jobs/* routes so older
# clients keep working until they migrate.


_NON_TERMINAL = ("queued", "running", "paused", "pending")
_RESUMABLE = ("paused", "cancelled", "error")


def _enqueue_resume(job: AiJob, resume_state: dict | None) -> None:
    """Re-enqueue a job with optional resume_state.

    Tries the RQ path first (if Redis + the worker module are reachable).
    Falls back to the in-process threaded runner from app.py so dev
    environments without an RQ worker still progress. Both paths read the
    same resume_state shape.
    """
    # Resolve language for resume — AiJob has no language column, so we
    # check resume_state first (where the orchestrator stashes it), then
    # user preference. Limitation: if neither source has it, language
    # defaults to None and the worker uses the orchestrator's fallback
    # (typically "id" based on the prompt filename). The original request
    # language is not accessible here because _enqueue_resume only receives
    # the job object and resume_state.
    _resume_lang = None
    # 1. Try resume_state (set by the chunked orchestrator).
    if resume_state and isinstance(resume_state, dict):
        _resume_lang = resume_state.get("language") or resume_state.get("lang")
    # 2. Try user's preferred_language.
    if not _resume_lang:
        try:
            from utils.database.models import User as _UserModel
            _u = _UserModel.query.get(job.user_id)
            if _u and _u.preferred_language:
                _resume_lang = _u.preferred_language
        except Exception:
            pass

    # Lazy imports so this module stays importable in alembic/test contexts.
    try:
        from rq import Queue

        from tools.paperfull.paper_worker import run_generate_paper

        _r = get_redis()
        if not _r:
            raise RuntimeError("Redis unavailable")
        q = Queue("paper", connection=_r)
        q.enqueue(
            run_generate_paper,
            job.id, job.user_id, job.paper_id, job.prompt or "",
            None, None, _resume_lang,
            resume_state=resume_state,
            job_timeout=3600,  # 60 min for resume
            result_ttl=3600,
        )
        publish_progress(
            job.id, {"stage": job.stage or "queued", "percent": int(job.progress or 0)}
        )
        return
    except Exception:
        pass

    # Fallback: kick off in-process via app._run_generate_full_job. This is the
    # same path used by the chat tool and /api/generate-full POST.
    try:
        import threading

        from main import _run_generate_full_job

        threading.Thread(
            target=_run_generate_full_job,
            args=(job.id, job.prompt or "", job.user_id),
            kwargs={
                "paper_id": job.paper_id,
                "resume_state": resume_state,
                "language": _resume_lang,
            },
            daemon=True,
        ).start()
    except Exception:
        # Surface in the row so the UI can show "Resume failed".
        job.status = "error"
        job.error = "resume failed: no worker available"
        safe_commit()


@jobs.route("/api/papers/<paper_id>/ai-jobs/active", methods=["GET"])
@jwt_required()
def ai_jobs_active(paper_id: str):
    """Return the most recent non-terminal generate_paper job for this paper.

    Used by the chat surface on paper-load to re-attach a progress bubble.
    Returns ``{"job": {...}}`` or ``{"job": null}``.
    """
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "paper not found"}), 404

    job = (
        AiJob.query.filter_by(user_id=user_id, paper_id=paper_id, kind="generate_paper")
        .filter(AiJob.status.in_(_NON_TERMINAL))
        .order_by(AiJob.started_at.desc())
        .first()
    )
    return jsonify({"job": job.to_dict() if job else None})


@jobs.route("/api/ai-jobs/<job_id>/cancel", methods=["POST"])
@jwt_required()
def ai_jobs_cancel(job_id: str):
    """Mirror of /api/jobs/<job_id>/cancel under the new path prefix."""
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    job = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "not found"}), 404
    if job.status in ("done", "cancelled"):
        return jsonify({"job": job.to_dict()})
    # Set the cancel flag for both the RQ worker (Redis key) and the chunked
    try:
        _r = get_redis()
        if _r:
            _r.setex(cancel_key(job_id), 3600, "1")
    except Exception:
        pass

    job.status = "cancelled"
    safe_commit()
    publish_progress(
        job_id,
        {
            "stage": job.stage or "cancelled",
            "percent": int(job.progress or 0),
            "status": "cancelled",
        },
    )
    return jsonify({"job": job.to_dict()})


@jobs.route("/api/ai-jobs/<job_id>/resume", methods=["POST"])
@jwt_required()
def ai_jobs_resume(job_id: str):
    """Resume a paused/cancelled/errored job from its last checkpoint."""
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    job = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "not found"}), 404
    if job.status not in _RESUMABLE:
        return (
            jsonify(
                {
                    "error": f"cannot resume from status={job.status}",
                    "job": job.to_dict(),
                }
            ),
            409,
        )

    result = job.result if isinstance(job.result, dict) else {}
    resume_state = {
        "chunks_done": list(result.get("chunks_done") or []),
        "partial_paper": result.get("partial_paper") or {},
    }

    # Clear any stale cancel flag — previous /cancel may have set it.
    try:
        _r = get_redis()
        if _r:
            _r.delete(cancel_key(job_id))
    except Exception:
        pass

    job.status = "queued"
    job.error = None
    safe_commit()

    _enqueue_resume(job, resume_state)
    return jsonify(
        {
            "job": job.to_dict(),
            "resume_state": {
                "chunks_done": resume_state["chunks_done"],
            },
        }
    )


@jobs.route("/api/ai-jobs/<job_id>/retry-section", methods=["POST"])
@jwt_required()
def ai_jobs_retry_section(job_id: str):
    """Retry a single chunk (e.g. ``section_3``).

    Removes the stage from ``chunks_done`` and, when the stage is a section,
    drops the matching entry from ``partial_paper.sections`` so the resumed
    run regenerates it cleanly. Other chunks stay cached.
    """
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    job = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "not found"}), 404
    if job.status not in _RESUMABLE + ("done",):
        return (
            jsonify(
                {
                    "error": f"cannot retry from status={job.status}",
                    "job": job.to_dict(),
                }
            ),
            409,
        )

    body = request.get_json(silent=True) or {}
    stage = (body.get("stage") or "").strip()
    if not stage:
        return jsonify({"error": "stage required"}), 400

    result = job.result if isinstance(job.result, dict) else {}
    chunks_done = [s for s in (result.get("chunks_done") or []) if s != stage]
    # Always re-run combine after a retry so the final assembly reflects the
    # regenerated chunk.
    chunks_done = [s for s in chunks_done if s != "combine"]
    partial = dict(result.get("partial_paper") or {})

    if stage.startswith("section_"):
        try:
            idx = int(stage.split("_", 1)[1]) - 1
            sections = list(partial.get("sections") or [])
            if 0 <= idx < len(sections):
                sections.pop(idx)
                partial["sections"] = sections
        except Exception:
            pass
    elif stage == "outline":
        partial.pop("outline", None)
        partial["sections"] = []
        # Outline drives every later chunk's context — invalidate them all.
        chunks_done = []
    elif stage == "references":
        partial.pop("references", None)

    job.result = {**result, "chunks_done": chunks_done, "partial_paper": partial}
    job.status = "queued"
    job.error = None
    job.stage = stage
    safe_commit()

    try:
        _r = get_redis()
        if _r:
            _r.delete(cancel_key(job_id))
    except Exception:
        pass

    _enqueue_resume(
        job,
        {
            "chunks_done": chunks_done,
            "partial_paper": partial,
        },
    )
    return jsonify({"job": job.to_dict()})


def _cleanup_orphaned_jobs(user_id: int) -> None:
    """Mark orphaned/stuck jobs as error.

    Orphaned = job in DB with status queued/running/pending but:
      - Not in Redis RQ queue (worker crashed/lost it), OR
      - Stuck at 0% progress for > 10 minutes with no RQ job backing it
    """
    try:
        from rq import Queue
        _r = get_redis()
        q = Queue("paper", connection=_r) if _r else None
        rq_job_ids = {j.id for j in q.jobs} if q else set()
    except Exception:
        rq_job_ids = set()

    now = datetime.now(timezone.utc)
    stuck_threshold = timedelta(minutes=10)

    active_jobs = AiJob.query.filter_by(
        user_id=user_id,
        kind="generate_paper"
    ).filter(
        AiJob.status.in_(["queued", "running", "pending"])
    ).all()

    for job in active_jobs:
        # Check if job is in RQ queue
        in_rq = job.id in rq_job_ids

        # Check age
        age = now - (job.started_at or job.updated_at or now)
        is_old = age > stuck_threshold

        # Mark as error if orphaned (not in RQ) AND old enough
        if not in_rq and is_old:
            job.status = "error"
            job.error = "Job lost — worker not available or crashed"
            safe_commit()
            logging.getLogger(__name__).warning(f"Auto-marked orphaned job {job.id} as error (age={age})")


@jobs.route("/api/me/ai-jobs/recent", methods=["GET"])
@jwt_required()
def ai_jobs_recent():
    """Recent jobs for the current user — feeds the inbox badge.

    Query params:
      - status: single status to filter on (default: ``done``)
      - since:  ISO 8601 timestamp; only jobs with started_at >= since
      - limit:  default 20, max 50
    """
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    status_filter = (request.args.get("status") or "").strip()
    since_raw = request.args.get("since")
    try:
        limit = min(50, max(1, int(request.args.get("limit", 20))))
    except (TypeError, ValueError):
        limit = 20

    q = AiJob.query.filter_by(user_id=user_id, kind="generate_paper")
    if status_filter:
        q = q.filter_by(status=status_filter)
    else:
        # Show all job states for the bell icon (active + done + failed)
        q = q.filter(AiJob.status.in_(["done", "running", "queued", "pending", "error", "cancelled"]))

    # Exclude orphan jobs: paper deleted or paper_id is null
    # Use JOIN instead of IN subquery for better performance
    valid_paper_ids = db.session.query(Paper.id).filter(Paper.user_id == user_id)
    q = q.filter(
        AiJob.paper_id.isnot(None),
        AiJob.paper_id.in_(valid_paper_ids),
    )

    if since_raw:
        try:
            # tolerate trailing 'Z'
            since_dt = datetime.fromisoformat(since_raw.replace("Z", "+00:00"))
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
            q = q.filter(AiJob.started_at >= since_dt)
        except ValueError:
            return jsonify({"error": "invalid since timestamp"}), 400

    rows = q.order_by(AiJob.started_at.desc()).limit(limit).all()
    return jsonify({"jobs": [r.to_dict() for r in rows]})


# ── Phase 2 — Direct SSE streaming generate (no RQ) ─────────────────────────
# Single-process paper generation that streams AI reasoning tokens directly
# to the browser via SSE. No Redis/RQ dependency — runs inline in the Flask
# worker. The frontend connects once and receives tokens as they arrive.


def _persist_paper_data(paper_id: str, user_id: int, paper_data: dict, max_retries: int = 3):
    """Persist generated paper JSON to the DB on a FRESH connection.

    During a long generate-stream (up to 900s) the original `paper` ORM object
    is bound to a DB connection that stays checked out for the whole stream.
    Postgres closes idle server-side connections, so committing through that
    stale handle raises `SSL connection has been closed unexpectedly`.

    Fix: roll back to release the stale connection back to the pool, then
    re-query the paper. With pool_pre_ping=True the pool validates (and
    transparently replaces) the dead connection on checkout, so the write
    lands on a live connection. Retries with backoff cover the race where the
    very first ping also trips on a half-dead handle.

    Returns (ok: bool, err: str | None).
    """
    from sqlalchemy.exc import DBAPIError, OperationalError

    last_err = None
    for attempt in range(max_retries):
        try:
            # Release whatever (possibly dead) connection the session holds so
            # the next query checks out a fresh, pre-pinged one.
            try:
                db.session.rollback()
            except Exception:
                pass
            p = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
            if not p:
                return False, "paper not found"
            
            # Preserve _data_texts if it exists in current paper.data
            # (pre-stored before generation, must not be lost)
            existing_data = p.data or {}
            if isinstance(existing_data, str):
                try:
                    import json
                    existing_data = json.loads(existing_data)
                except Exception:
                    existing_data = {}
            
            # Merge: new data overwrites, but preserve metadata + _data_texts from
            # existing paper. _normalize_paper_shape only returns content fields
            # (title/abstract/sections/...), so user-set metadata like language,
            # journal, citation_style would be LOST on regeneration without this.
            paper_data = {**paper_data}
            for _meta_key in ('language', 'journal', 'citation_style'):
                if _meta_key not in paper_data and _meta_key in existing_data:
                    paper_data[_meta_key] = existing_data[_meta_key]
            if '_data_texts' not in paper_data and '_data_texts' in existing_data:
                paper_data['_data_texts'] = existing_data['_data_texts']
                paper_data['_data_files_count'] = existing_data.get('_data_files_count', 0)
            
            p.data = paper_data
            p.title = (paper_data.get("title") or "").strip() or p.title or "Untitled"
            p.updated_at = datetime.now(timezone.utc)
            safe_commit()
            return True, None
        except (OperationalError, DBAPIError) as e:
            last_err = e
            try:
                db.session.rollback()
            except Exception:
                pass
            log.warning(
                "Paper save attempt %d/%d failed for %s (stale connection): %s",
                attempt + 1, max_retries, paper_id, e,
            )
            time.sleep(0.4 * (attempt + 1))
        except Exception as e:
            try:
                db.session.rollback()
            except Exception:
                pass
            log.warning("Paper persist failed for %s: %s", paper_id, e)
            return False, "database error"
    return False, "database error"


@jobs.route("/api/papers/<paper_id>/generate-status", methods=["GET"])
@jwt_required()
def generate_status(paper_id: str):
    """Read the LIVE position of an in-flight paperfull generation.

    Mirrors the chat /stream-status endpoint: returns the incremental
    reasoning + content snapshot written to Redis by generate-stream, so a
    browser that refreshed or lost connection can resume showing HOW FAR the
    backend has gotten (not just wait for the finished paper in the DB).

    Returns:
        status:    'streaming' | 'done' | 'error' | 'not_found'
        reasoning: accumulated reasoning/thinking text so far
        content:   accumulated completion text so far
        error:     error message (if status == 'error')
        started_at: ISO timestamp when streaming began
    """
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"status": "not_found"}), 404

    try:
        _r = get_redis()
        raw = _r.get(f"paperfull:stream:{paper_id}") if _r else None
        if not raw:
            return jsonify({"status": "not_found"})
        state = json.loads(raw)
        return jsonify({
            "status": state.get("status", "not_found"),
            "reasoning": state.get("reasoning", ""),
            "content": state.get("content", ""),
            "error": state.get("error"),
            "started_at": state.get("started_at"),
        })
    except Exception as e:
        log.warning("Failed to get paperfull stream status: %s", e)
        return jsonify({"status": "not_found"})


@jobs.route("/api/papers/<paper_id>/generate-stream", methods=["POST"])
@jwt_required()
def generate_stream(paper_id: str):
    """Stream paper generation directly — single process, no queue.

    POST body (JSON or multipart):
        prompt: str        — topic / title description
        topic: str|null    — topic guide slug
        style: str|null    — citation style slug
        language: str|null — 'id' or 'en'
        paper_kind: str|null — 'review' or 'regular' (auto-detect if omitted)
        generate_images: bool — true (default) / false to skip image gen

    Returns SSE stream with events:
        event: thinking   data: {"token": "..."}         — reasoning tokens
        event: content    data: {"token": "..."}         — output tokens
        event: done       data: {"paper": {...}}          — final paper JSON
        event: error      data: {"error": "..."}          — generation error
    """
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    # Validate paper_id format to prevent path traversal
    import re as _re
    if not _re.match(r"^[A-Za-z0-9_-]{1,64}$", paper_id):
        return jsonify({"error": "Invalid paper id"}), 400

    # ── Quota gate — block generate if insufficient tokens ────────────
    from utils.quota import quota_exceeded
    exceeded, info = quota_exceeded(user_id)
    if exceeded:
        _info = dict(info) if isinstance(info, dict) else {"error": str(info)}
        _info["needs_purchase"] = "true"
        return jsonify(_info), 429

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "paper not found"}), 404

    # Prevent concurrent generation on same paper
    active_job = AiJob.query.filter_by(
        paper_id=paper_id,
        user_id=user_id
    ).filter(
        AiJob.status.in_(["queued", "running", "pending"])
    ).first()
    if active_job:
        return jsonify({
            "error": "Paper ini sedang dalam proses generate. Tunggu sampai selesai.",
            "existing_job_id": active_job.id,
        }), 409

    # Parse request body
    data_texts: list[str] = []
    reference_texts: list[str] = []
    selected_drafts: list | str | None = None
    revisi_semua = False
    regenerate_images = False
    
    # Force log this
    import logging as _log_module
    _log_module.getLogger(__name__).warning(f"=== GENERATE-STREAM CALLED for paper {paper_id} ===")
    _log_module.getLogger(__name__).warning(f"content_type: {request.content_type}")
    
    log.info("[paperfull] content_type: %s", request.content_type)
    if request.content_type and "multipart/form-data" in request.content_type:
        prompt = (request.form.get("prompt") or "").strip()
        topic = request.form.get("topic") or None
        style = request.form.get("style") or None
        language = request.form.get("language") or None
        paper_kind_raw = request.form.get("paper_kind") or None
        paper_kind = paper_kind_raw if paper_kind_raw in ("review", "regular") else None
        generate_images_raw = request.form.get("generate_images", "true").lower()
        generate_images = generate_images_raw != "false"
        revisi_semua_raw = request.form.get("revisi_semua", "false").lower()
        revisi_semua = revisi_semua_raw == "true"
        regenerate_images_raw = request.form.get("regenerate_images", "false").lower()
        regenerate_images = regenerate_images_raw == "true"
        # Selected chat drafts. Accept JSON list (legacy) or plain text block
        # from PaperfullTab when multipart upload is used.
        _sd_raw = request.form.get("selected_drafts")
        if _sd_raw:
            try:
                selected_drafts = json.loads(_sd_raw)
            except (json.JSONDecodeError, TypeError):
                selected_drafts = _sd_raw
        # Two separate buckets:
        #   data_files      → docx/csv/xlsx/pdf yang berisi DATA mentah (untuk
        #                      tabel/grafik). Diproses sebagai sumber data.
        #   reference_files → paper sitasi ATAU draft user. Diproses sebagai
        #                      referensi/konteks penulisan.
        # Backward-compat: field lama "files" diperlakukan sebagai referensi.
        from main import _extract_texts_from_files
        data_uploads = []
        ref_uploads = []
        try:
            data_uploads = request.files.getlist("data_files")
            ref_uploads = request.files.getlist("reference_files")
            legacy_uploads = request.files.getlist("files")
            log.info("[paperfull] data_uploads: %d files, ref_uploads: %d files", len(data_uploads), len(ref_uploads))
            if data_uploads:
                data_texts = _extract_texts_from_files(data_uploads)
                log.info("[paperfull] extracted %d data_texts from files, total chars: %d", len(data_texts), sum(len(t) for t in data_texts))
                # Write to debug log
                import logging as _log_module2
                _log_module2.getLogger(__name__).warning(f"data_uploads: {len(data_uploads)} files, data_texts: {len(data_texts)} items")
            if ref_uploads:
                reference_texts = _extract_texts_from_files(ref_uploads)
            if legacy_uploads and not ref_uploads:
                reference_texts += _extract_texts_from_files(legacy_uploads)
            # Pre-extracted texts (virtual entries: existing files, data analysis, drafts)
            # sent as JSON string arrays from frontend when no File object is available.
            _dt_raw = request.form.get("data_texts")
            if _dt_raw:
                try:
                    _dt = json.loads(_dt_raw)
                    if isinstance(_dt, list):
                        data_texts += [str(t) for t in _dt if t]
                except (json.JSONDecodeError, TypeError):
                    pass
            _rt_raw = request.form.get("reference_texts")
            if _rt_raw:
                try:
                    _rt = json.loads(_rt_raw)
                    if isinstance(_rt, list):
                        reference_texts += [str(t) for t in _rt if t]
                except (json.JSONDecodeError, TypeError):
                    pass
        except Exception as _fe:
            log.warning("generate-stream file extraction failed for paper %s: %s", paper_id, _fe)

        # ── Persist uploaded files to PaperFile DB + user storage ────────
        # Files uploaded during paperfull generate were only extracted for text
        # but never saved. Now we save them so they appear in the file list.
        try:
            from utils.database.models import PaperFile
            from utils.core.user_storage import save_file_as_txt, get_username as _pf_get_username
            _pf_username = _pf_get_username(user_id=user_id)
            _pf_judul = paper.title if paper else "untitled"
            _all_uploads = [
                (data_uploads, data_texts, "data"),
                (ref_uploads, reference_texts, "reference"),
            ]
            for _file_list, _text_list, _bucket in _all_uploads:
                for _idx, _fobj in enumerate(_file_list):
                    _orig_name = _fobj.filename or f"upload_{_idx}"
                    _ext = Path(_orig_name).suffix.lower() if _orig_name else ".txt"
                    if _idx < len(_text_list) and _text_list[_idx]:
                        _extracted = _text_list[_idx]
                        # Save extracted text as .txt to user storage
                        try:
                            save_file_as_txt(_pf_username, _pf_judul, _extracted, _orig_name)
                        except Exception:
                            pass
                        # Save to PaperFile DB — upsert by original_name to
                        # avoid duplicate rows when the same file is uploaded
                        # again (e.g. retry after network hiccup).
                        _pf_existing = PaperFile.query.filter_by(
                            paper_id=paper_id,
                            user_id=user_id,
                            original_name=_orig_name[:255],
                        ).first()
                        if _pf_existing:
                            _pf_existing.extracted_text = _extracted
                            _pf_existing.size_bytes = len(_extracted.encode("utf-8"))
                        else:
                            _hash_name = f"{uuid.uuid4().hex}{_ext}"
                            _pf_entry = PaperFile(
                                paper_id=paper_id,
                                user_id=user_id,
                                filename=_hash_name,
                                original_name=_orig_name[:255],
                                ext=_ext,
                                size_bytes=len(_extracted.encode("utf-8")),
                                file_path="",
                                extracted_text=_extracted,
                            )
                            db.session.add(_pf_entry)
            safe_commit()
            db.session.remove()  # Release DB connection back to pool (BUG-31: avoid idle 900s timeout)
            log.info("[paperfull] Persisted %d data + %d ref files to DB for paper %s",
                     len(data_uploads), len(ref_uploads), paper_id)
        except Exception as _pf_e:
            log.warning("[paperfull] Failed to persist files to DB for paper %s: %s", paper_id, _pf_e)
            try:
                db.session.rollback()
            except Exception:
                pass
    else:
        body = request.get_json(silent=True) or {}
        prompt = (body.get("prompt") or "").strip()
        topic = body.get("topic") or None
        style = body.get("style") or None
        language = body.get("language") or None
        paper_kind_raw = body.get("paper_kind") or None
        paper_kind = paper_kind_raw if paper_kind_raw in ("review", "regular") else None
        generate_images_raw = str(body.get("generate_images", True)).lower()
        generate_images = generate_images_raw != "false"
        revisi_semua = bool(body.get("revisi_semua", False))
        regenerate_images = bool(body.get("regenerate_images", False))
        # JSON path: allow pre-extracted texts to be passed directly.
        data_texts = body.get("data_texts") or []
        reference_texts = body.get("reference_texts") or []
        selected_drafts = body.get("selected_drafts")

    # ── Pre-store data_texts to Paper.data BEFORE generation ─────────────
    # This ensures data persists even if closure loses the variable.
    # The gen() closure will re-inject after _normalize_paper_shape, but
    # this is the safety net.
    import logging as _prestore_log
    _prestore_log.getLogger(__name__).warning(f"=== PRE-STORE CHECK: data_texts={len(data_texts) if data_texts else 0} items for paper {paper_id}")
    if data_texts:
        try:
            existing_data = paper.data or {}
            if isinstance(existing_data, str):
                try:
                    existing_data = json.loads(existing_data)
                except (json.JSONDecodeError, TypeError):
                    existing_data = {}
            existing_data["_data_texts"] = data_texts
            existing_data["_data_files_count"] = len([t for t in data_texts if t and t.strip()])
            paper.data = existing_data
            safe_commit()
            db.session.remove()  # Release DB connection back to pool (avoid leak in JSON pre-store branch)
            log.info("[paperfull] Pre-stored %d data_texts to paper.data for paper %s",
                     len(data_texts), paper_id)
            _prestore_log.getLogger(__name__).warning(f"=== PRE-STORE SUCCESS: saved {len(data_texts)} items")
        except Exception as _pre_e:
            log.warning("[paperfull] Failed to pre-store data_texts: %s", _pre_e)
            _prestore_log.getLogger(__name__).warning(f"=== PRE-STORE FAILED: {_pre_e}")
            try:
                db.session.rollback()
            except Exception:
                pass
    else:
        _prestore_log.getLogger(__name__).warning(f"=== PRE-STORE SKIPPED: no data_texts")

    if not prompt:
        return jsonify({"error": "prompt required"}), 400

    # ── Handle Re-generate Images only (no paper generation) ────────────
    if regenerate_images:
        from utils.database.models import PaperImage, ImageGenJob  # noqa: PLC0415
        # Same behavior as /api/image-jobs/regenerate, kept inline to support
        # clients that submit via Generate Full's generate-stream route.
        import uuid as _uuid  # noqa: PLC0415

        images = PaperImage.query.filter_by(paper_id=paper_id, user_id=user_id).all()
        if not images:
            return jsonify({"error": "Tidak ada image untuk di-re-generate"}), 404

        # Recover prompt + target_path from previous completed ImageGenJob
        _prev = (
            ImageGenJob.query
            .filter(ImageGenJob.paper_id == paper_id, ImageGenJob.user_id == user_id, ImageGenJob.status == "done")
            .order_by(ImageGenJob.finished_at.desc())
            .all()
        )
        _jmap: dict[int, dict] = {}
        for _j in _prev:
            if _j.image_id and _j.image_id not in _jmap:
                _jmap[_j.image_id] = {"prompt": _j.prompt or "", "target_path": _j.target_path or ""}

        _specs = []
        for img in images:
            info = _jmap.get(img.id, {})
            _prompt = info.get("prompt", "")
            _tpath = info.get("target_path", "") or img.original_name
            if not _prompt:
                continue
            _specs.append({"prompt": _prompt, "target_path": _tpath})
            # DO NOT delete old PaperImage/file here — worker will replace on success

        if not _specs:
            return jsonify({"error": "Tidak ada prompt yang bisa di-recover"}), 404

        created_jobs = []
        for spec in _specs:
            job = ImageGenJob(
                id=_uuid.uuid4().hex,
                user_id=user_id,
                paper_id=paper_id,
                prompt=spec["prompt"],
                target_path=spec["target_path"][:500] if spec["target_path"] else None,
                status="queued",
            )
            db.session.add(job)
            created_jobs.append(job)

        safe_commit()

        try:
            from tools.image_generation.worker import submit_now  # noqa: PLC0415
            for job in created_jobs:
                submit_now(job.id)
        except Exception:
            log.exception("submit_now failed (jobs will still run via dispatcher poll)")

        return jsonify({
            "jobs": [{"id": j.id, "paper_id": j.paper_id, "status": j.status}
                     for j in created_jobs]
        })

    # New generate session must not inherit stale Redis snapshot from the previous run.
    # ponytail: key is per-paper; upgrade to per-run ids if concurrent same-paper generate is ever allowed.
    try:
        _r = get_redis()
        if _r:
            _r.delete(f"paperfull:stream:{paper_id}")
    except Exception:
        pass

    # ── Register an AiJob so this generation shows up in the notification
    #    bell immediately (kind=generate_paper is what /api/me/ai-jobs/recent
    #    polls). The inline SSE path previously created no job, so paperfull
    #    runs never appeared in the bell. We mark it 'running' up-front and
    #    flip it to done/error at finalize.
    _bell_job_id = uuid.uuid4().hex[:16]
    try:
        _bell_job = AiJob(
            id=_bell_job_id,
            user_id=user_id,
            paper_id=paper_id,
            kind="generate_paper",
            status="running",
            progress=1,
            stage="generating",
            prompt=prompt[:4000],
        )
        db.session.add(_bell_job)
        safe_commit()
    except Exception as _e:
        try:
            db.session.rollback()
        except Exception:
            pass
        log.warning("Failed to register bell job for paper %s: %s", paper_id, _e)
        _bell_job_id = None

    def _update_bell_job(status: str, progress: int = 100, error: str | None = None):
        """Flip the bell AiJob to a terminal state on a fresh connection."""
        if not _bell_job_id:
            return
        from sqlalchemy.exc import DBAPIError, OperationalError
        for _attempt in range(3):
            try:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                j = AiJob.query.filter_by(id=_bell_job_id).first()
                if not j:
                    return
                j.status = status
                j.progress = progress
                j.stage = status
                if error:
                    j.error = error[:2000]
                j.updated_at = datetime.now(timezone.utc)
                safe_commit()
                return
            except (OperationalError, DBAPIError) as _e:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                log.warning("Bell job update attempt %d failed (stale conn): %s", _attempt + 1, _e)
                time.sleep(0.3 * (_attempt + 1))
            except Exception:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                log.exception("Bell job update failed (non-retryable)")
                return

    def gen():
        """Generator that streams AI tokens directly to the browser."""
        import json as _json
        import os as _os
        import time as _time
        from pathlib import Path as _Path

        # Early-init accumulators so GeneratorExit handler can always reference them (BUG-35).
        full_content = ""
        reasoning_acc = ""

        try:
            # ── Load prompt files (language-aware) ─────────────────────
            prompt_dir = _Path(__file__).resolve().parent / "prompt"

            # Determine language: request param > paper data > journal template > user DB > default "id"
            _lang = language
            _from_paper = False
            _from_user_db = False
            if not _lang and paper_id:
                try:
                    _paper = Paper.query.get(paper_id)
                    if _paper and isinstance(_paper.data, dict):
                        pl = _paper.data.get("language")
                        if pl in ("en", "id"):
                            _lang = pl
                            _from_paper = True
                        # Step 3: Fall back to journal template (only if paper has no language set)
                        if not _lang and _paper.data.get("journal"):
                            try:
                                from tools.Journal.template_registry import get_template as _get_tmpl
                                _tmpl = _get_tmpl(_paper.data["journal"])
                                if _tmpl:
                                    _tl = _tmpl.language.lower()
                                    if _tl.startswith("english"):
                                        _lang = "en"
                                    elif _tl.startswith("indonesian"):
                                        _lang = "id"
                            except Exception:
                                pass
                except Exception:
                    pass
            # User DB: only as fallback if paper/journal didn't set language
            if not _lang and not _from_paper:
                try:
                    from utils.database.models import User as _UserModel
                    _lu = _UserModel.query.get(user_id)
                    if _lu and _lu.preferred_language:
                        _lang = _lu.preferred_language
                        _from_user_db = True
                except Exception:
                    pass
            _lang = _lang or "id"

            # Load single unified prompt file (language injected at runtime)
            prompt_file = prompt_dir / "prompt.txt"
            humanize_file = prompt_dir / "humanize.txt"

            if not prompt_file.exists():
                yield f"event: error\ndata: {_json.dumps({'error': 'prompt.txt not found'})}\n\n"
                return

            # Inject language directive at the top
            if _lang == "en":
                lang_instruction = "⚠️ LANGUAGE: This paper MUST be written ENTIRELY in ENGLISH.\n\n"
            else:
                lang_instruction = "⚠️ BAHASA: Paper ini WAJIB ditulis SELURUHNYA dalam BAHASA INDONESIA.\n\n"

            system_parts = [lang_instruction + prompt_file.read_text(encoding="utf-8")]
            if humanize_file.exists():
                system_parts.append(humanize_file.read_text(encoding="utf-8"))

            # Language-specific section titles template
            lang_template = prompt_dir / f"{_lang}.json"
            if lang_template.exists():
                system_parts.append(f"USE THESE SECTION TITLES:\n{lang_template.read_text(encoding='utf-8')}\nThe section titles above MUST be used exactly as shown.")

            # Style guide
            if style:
                # Whitelist: only allow known style slugs
                _ALLOWED_STYLES = {
                    'APA', 'MLA', 'CHICAGO', 'HARVARD', 'VANCOUVER', 'IEEE',
                    'AMA', 'TURABIAN', 'OSCOLA', 'AGLC', 'CEUR', 'SPRINGER',
                    'MDPI', 'LNCS', 'SPRINGERNATURE', 'NATURE', 'ELSEVIER',
                    'ACM', 'IEEE-COMPUTER', 'SPRINGER-LNCS', 'SPRINGER-LNBIP',
                    'SPRINGER-STUDIES', 'LIPICS', 'NATURALSCIENCES', 'E3S',
                    'DRF', 'USCS', 'AMORI', 'ICET', 'ICIMECE', 'EASR', 'ITM',
                }
                style_key = style.upper().strip()
                if style_key in _ALLOWED_STYLES:
                    style_file = prompt_dir / "style" / f"{style_key}.txt"
                    if style_file.exists():
                        resolved = style_file.resolve()
                        if resolved.is_relative_to((prompt_dir / "style").resolve()):
                            system_parts.append(f"## CITATION STYLE GUIDE — {style_key}\n" + resolved.read_text(encoding="utf-8"))

            # Paper review mode: only active when the UI explicitly sends paper_kind=review
            # or the title/prompt asks for a review article. Reference PDFs alone must not
            # turn a regular paper into a paper review.
            _review_intent_text = f"{prompt} {custom_prompt or ''}".lower()
            _review_keywords = (
                "paper review", "review paper", "systematic review", "narrative review",
                "scoping review", "bibliometric review", "meta-analysis", "meta analysis",
                "review artikel", "review literatur", "studi pustaka", "kajian pustaka",
            )
            _is_review_mode = paper_kind == "review" or any(k in _review_intent_text for k in _review_keywords)
            if _is_review_mode:
                review_file = prompt_dir / "topic" / "review.txt"
                if review_file.exists():
                    system_parts.append("## TOPIC GUIDE (PAPER REVIEW MODE — WAJIB REVIEW, BUKAN REGULAR PAPER)\n" + review_file.read_text(encoding="utf-8"))
            else:
                system_parts.append(
                    "## REGULAR PAPER MODE — NOT A PAPER REVIEW\n"
                    "Reference PDFs and checked literature are citation/context sources only. "
                    "Do NOT structure the manuscript as a paper review, systematic review, SLR, "
                    "or literature-review article unless paper_kind=review is explicitly set. "
                    "Do NOT write phrases such as 'this review', 'paper review', 'systematic review', "
                    "'summary of papers', or 'reviewed studies' in Abstract/Methods/Results. "
                    "Use normal sections: Introduction, Literature Review, Methodology, Results and Discussion, Conclusion.\n"
                )

            # Topic guide
            if topic:
                # Whitelist: only allow known topic slugs
                _ALLOWED_TOPICS = {
                    'artificial-intelligence', 'machine-learning', 'deep-learning',
                    'natural-language-processing', 'data-science', 'computer-vision',
                    'robotics', 'cybersecurity', 'blockchain', 'cloud-computing',
                    'iot', 'hci', 'software-engineering', 'bioinformatics',
                    'environmental-science', 'climate-change', 'renewable-energy',
                    'sustainable-development', 'water-resources', 'agriculture',
                    'public-health', 'epidemiology', 'healthcare', 'medicine',
                    'economics', 'finance', 'management', 'marketing',
                    'education', 'psychology', 'sociology', 'law',
                    'materials-science', 'chemistry', 'physics', 'biology',
                    'mathematics', 'engineering', 'mechanical-engineering',
                    'electrical-engineering', 'civil-engineering', 'chemical-engineering',
                    'renewable-energy-engineering', 'biomedical-engineering',
                    'aerospace', 'food-science', 'pharmacy', 'dentistry',
                    'nursing', 'veterinary', 'architecture', 'urban-planning',
                    'supply-chain', 'logistics', 'tourism', 'hospitality',
                }
                topic_key = topic.strip().lower().replace(' ', '-')
                if topic_key in _ALLOWED_TOPICS:
                    topic_file = prompt_dir / "topic" / f"{topic_key}.txt"
                    if topic_file.exists():
                        resolved = topic_file.resolve()
                        if resolved.is_relative_to((prompt_dir / "topic").resolve()):
                            system_parts.append(f"## TOPIC GUIDE — {topic_key}\n" + resolved.read_text(encoding="utf-8"))

            # Inject user preferences (name, full name, institution, language)
            try:
                from utils.database.models import User as UserModel
                current_user = UserModel.query.get(user_id)
                if current_user:
                    prefs = []
                    nickname = current_user.nickname or current_user.name
                    if nickname:
                        prefs.append(f"- Panggil user dengan nama: **{nickname}**")
                    full_name = current_user.name or ""
                    if full_name and full_name != nickname:
                        prefs.append(f"- Nama lengkap user: **{full_name}**")
                    institution = current_user.institution or ""
                    if institution:
                        prefs.append(f"- Institusi user: **{institution}**")
                    lang = _lang
                    if lang == "en":
                        prefs.append("- SELALU gunakan Bahasa Inggris (English) untuk respons dan penulisan paper, kecuali user meminta bahasa lain.")
                    else:
                        prefs.append("- Gunakan Bahasa Indonesia sebagai bahasa utama untuk respons dan penulisan paper.")
                    if prefs:
                        system_parts.append("## User Preferences\n" + "\n".join(prefs) + "\n")
            except Exception as e:
                import logging as _logging
                _logging.getLogger(__name__).warning("Failed to inject user preferences into generate-stream: %s", e)

            system_prompt = "\n\n".join(system_parts)

            # ── Build user message ────────────────────────────────────
            user_parts = [f"Topic / title: {prompt}"]

            # Inject DATA sources (docx/csv/xlsx/pdf berisi data mentah). AI
            # harus memakai angka-angka ini untuk tabel + item `gambar`
            # ber-prompt chart-style (grafik). JANGAN mengarang data bila ada.
            print(f"[paperfull DEBUG gen] data_texts available: {len(data_texts) if data_texts else 0} items")
            if data_texts:
                for i, t in enumerate(data_texts[:2]):
                    print(f"[paperfull DEBUG gen]   data_texts[{i}]: {t[:100]}...")
            if data_texts:
                _data_blob = "\n\n".join(t for t in data_texts if t and t.strip())
                if _data_blob.strip():
                    # Count actual files: each entry from _extract_texts_from_files
                    # starts with "=== Extracted from: filename ==="
                    _file_markers = re.findall(r'=== Extracted from: .+? ===', _data_blob)
                    _n_files = len(_file_markers) if _file_markers else len([t for t in data_texts if t and t.strip()])
                    user_parts.append(
                        "## 📊 DATA SUMBER — INI DATA BENERAN (WAJIB DIPAKAI — ANGKA PERSIS)\n"
                        f"User meng-upload {_n_files} file DATA BENERAN (Excel/CSV/data numerik). "
                        "Berikut data mentah yang diunggah.\n"
                        "⚠️ INI SATU-SATUNYA SUMBER DATA untuk section 4. "
                        "Bukan referensi paper, bukan literatur.\n"
                        "WAJIB gunakan ANGKA/nilai PERSIS dari data ini untuk:\n"
                        "1. Isi tabel (Headers + Rows) — JANGAN pakai placeholder (X1, a1, dst)!\n"
                        "2. Narasi analisis — kutip angka spesifik dari data\n"
                        "3. Rumus/persamaan — gunakan parameter aktual dari data\n"
                        f"\nATURAN SECTION 4: Untuk {_n_files} file data, WAJIB buat:\n"
                        f"- MINIMAL {_n_files * 2} tabel (2 per file, bahas data rinci per file)\n"
                        f"- MINIMAL {_n_files * 2} grafik data (2 per file)\n"
                        "Setiap tabel WAJIB berisi data REAL dari Excel (angka persis).\n"
                        "Setiap grafik (id \"gambar\" di section4) WAJIB punya Prompt yang DIISI\n"
                        "SPESIFIKASI GRAFIK LENGKAP (bukan kosong!) mencakup:\n"
                        "  1. JENIS GRAFIK: bar / line / scatter / pie / stacked_bar / heatmap / area\n"
                        "  2. DATA LENGKAP: TULIS SEMUA angka/nilai PERSIS dari Excel dalam format\n"
                        "     terstruktur (markdown tabel atau key-value pairs)\n"
                        "  3. AXIS LABELS: X-axis = \"...\", Y-axis = \"...\"\n"
                        "  4. TITLE: Judul grafik yang jelas\n"
                        "  5. LEGEND/CATEGORIES: Kategori atau series yang ditampilkan\n"
                        "  6. STYLE: Warna, orientasi, grid on/off\n"
                        "JANGAN mengarang data lain. JANGAN gunakan variabel placeholder.\n"
                        "⛔ INI BUKAN REFERENSI — ini DATA untuk tabel dan grafik section 4.\n\n"
                        "Data dalam format markdown tabel:\n\n" + _data_blob
                    )

            # Inject REFERENSI (paper sitasi atau draft user). Dipakai sebagai
            # konteks penulisan + sumber sitasi, BUKAN sebagai data grafik.
            if reference_texts:
                _ref_blob = "\n\n".join(t for t in reference_texts if t and t.strip())
                if _ref_blob.strip():
                    user_parts.append(
                        "## REFERENSI / DRAFT (WAJIB DIGUNAKAN — BUKAN DATA)\n"
                        "Berikut paper referensi/sitasi atau draft milik user. WAJIB:\n"
                        "1. Pakai sebagai konteks penulisan dan arah pembahasan\n"
                        "2. Gunakan sebagai SUMBER SITASI di References section\n"
                        "3. ⛔ INI BUKAN DATA untuk section 4 (Results)!\n"
                        "   JANGAN gunakan angka/hasil dari referensi sebagai data tabel/grafik di section 4.\n"
                        "   Section 4 HANYA boleh pakai data dari ## DATA SUMBER.\n"
                        "   Jika ## DATA SUMBER TIDAK muncul → section 4 WAJIB pakai placeholder (x1, x2, x3, dst).\n"
                        "4. Kutipan data dari referensi TETAP BOLEH di narasi Literature Review (section 2)\n"
                        "   sebagai perbandingan metode/state-of-the-art — TAPI JANGAN sebagai data eksperimen.\n"
                        "5. JANGAN abaikan isi referensi, tetapi tetap tulis REGULAR PAPER jika paper_kind bukan review.\n"
                        "6. Setiap paragraf sitasi minimal 1-3 paper dari referensi ini.\n"
                        "7. Untuk REGULAR PAPER: jangan menyebut output sebagai review/ringkasan paper.\n"
                        "8. WAJIB: Total references section minimal 36 paper (Regular Article)\n\n"
                        + _ref_blob
                    )

            # Auto-inject CHECKED LITERATURE (dari tab Literatur).
            # User hanya perlu check di tab Literatur — otomatis masuk prompt.
            try:
                from utils.database.models import LiteratureItem as LitItem
                _checked_lit = LitItem.query.filter_by(
                    paper_id=paper_id,
                    user_id=user_id,
                    is_checked=True,
                ).order_by(LitItem.score_total.desc().nullslast()).all()
                if _checked_lit:
                    _lit_parts = []
                    for _lit in _checked_lit:
                        _authors_str = ", ".join(_lit.authors) if _lit.authors else "—"
                        _year_str = str(_lit.year) if _lit.year else "—"
                        _pub_str = _lit.publisher or _lit.venue or "—"
                        _doi_str = _lit.doi or "—"
                        _abstract_str = _lit.abstract or "—"
                        _lit_parts.append(
                            f"--- Literatur: {_lit.title} ---\n"
                            f"Judul: {_lit.title}\n"
                            f"Penulis: {_authors_str}\n"
                            f"Tahun: {_year_str}\n"
                            f"Penerbit: {_pub_str}\n"
                            f"DOI: {_doi_str}\n"
                            f"Abstract: {_abstract_str}\n"
                            f"——— akhir literatur ———"
                        )
                    _lit_blob = "\n\n".join(_lit_parts)
                    user_parts.append(
                        "## LITERATUR (CHECKED — WAJIB DIGUNAKAN SEBAGAI REFERENSI)\n"
                        f"User telah men-checklist {len(_checked_lit)} paper dari tab Literatur. "
                        "Jika paper_kind=review, manuscript WAJIB benar-benar mereview semua paper ini secara kritis. "
                        "Jika paper_kind bukan review, gunakan sebagai referensi pendukung saja, bukan mengubah artikel menjadi paper review. "
                        "WAJIB:\n"
                        "1. Gunakan SEMUA paper ini sebagai SUMBER SITASI di References section\n"
                        "2. Sitasi paper ini di narasi sesuai konteks yang relevan\n"
                        "3. JANGAN mengabaikan satupun — semua harus disitasi\n"
                        "4. JANGAN memfabrikasi referensi lain jika paper ini sudah cukup\n"
                        "5. Setiap paragraf sitasi minimal 1-3 paper dari daftar ini\n\n"
                        + _lit_blob
                    )
                    log.info(
                        "Auto-injected %d checked literature items into generate-stream for paper %s",
                        len(_checked_lit), paper_id,
                    )
            except Exception as _lit_e:
                log.warning("Failed to auto-inject checked literature: %s", _lit_e)

            # Inject selected CHAT DRAFTS (user-curated snippets exported from
            # chat, picked via the checkbox selector in PaperfullTab). Resolved
            # by name → formatted block. This is the path the frontend actually
            # uses (generate-stream); enqueue_generate has its own copy.
            # selected_drafts can be:
            #   - str: pre-formatted text block (new frontend sends drafts as text directly)
            #   - list: JSON array of draft names (legacy, fetch from DB)
            if selected_drafts:
                if isinstance(selected_drafts, str):
                    # Pre-formatted text from frontend (drafts already embedded in referenceFiles)
                    _draft_block = selected_drafts
                else:
                    # Legacy: list of names → fetch from DB
                    try:
                        from tools.chat.drafts import get_drafts_by_names
                        _draft_block = get_drafts_by_names(
                            paper_id, user_id, selected_drafts, max_items=10
                        )
                    except Exception as _de:
                        log.warning("Failed to inject selected drafts into generate-stream: %s", _de)
                        _draft_block = None
                if _draft_block:
                    user_parts.append(
                        "## Chat Drafts (user-selected context)\n"
                        "Berikut draft hasil diskusi chat yang dipilih user. Pakai "
                        "sebagai konteks penulisan dan arah pembahasan.\n\n" + _draft_block
                    )
                    log.info(
                        "Injected draft(s) into generate-stream for paper %s",
                        paper_id,
                    )

            # ── REVISI SEMUA: inject existing paper JSON ──────────────
            if revisi_semua:
                try:
                    _existing = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
                    if _existing and _existing.data:
                        _ed = _existing.data if isinstance(_existing.data, dict) else _json.loads(_existing.data)
                        # Strip internal keys (_data_texts, _data_files_count, etc.)
                        _ed_clean = {k: v for k, v in _ed.items() if not k.startswith("_")}
                        _existing_json = _json.dumps(_ed_clean, ensure_ascii=False, indent=2)
                        user_parts.append(
                            "## EXISTING PAPER (REVISI SEMUA — PERBAIKI TOTAL)\n"
                            "Berikut adalah paper JSON yang sudah ada. Kamu WAJIB merevisi TOTAL:\n"
                            "1. Perbaiki SEMUA aspek yang kurang — struktur, argumen, data, narasi, gambar\n"
                            "2. Jika ada data_teks yang diunggah, PASTIKAN semua angka/tabel dari data\n"
                            "   tersebut masuk ke paper yang direvisi\n"
                            "3. Jika ada literatur yang di-check, PASTIKAN semua disitasi\n"
                            "4. JANGAN hanya copy-paste — revisi bermakna, perbaiki kualitas\n"
                            "5. Output TETAP full paper JSON lengkap (bukan diff/patch)\n\n"
                            + _existing_json
                        )
                        log.info("Injected existing paper JSON for revisi_semua (paper %s, %d chars)",
                                 paper_id, len(_existing_json))
                except Exception as _re:
                    log.warning("Failed to inject existing paper JSON for revisi_semua: %s", _re)

            user_parts.append(
                "Generate the complete paper following the system prompt schema. "
                "Return ONLY a JSON object — no markdown fences, no commentary."
            )
            user_message = "\n\n".join(user_parts)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]

            # ── AI API config (per-index endpoint chain) ──────────────
            from utils.ai_tools.model_router import route_generate_call
            from utils.ai_tools.model_config import get_endpoint_chain
            from utils.core.env_loader import load_app_env
            load_app_env()

            _chain = get_endpoint_chain(heavy=True)
            if not _chain:
                yield f"event: error\ndata: {_json.dumps({'error': 'AIOTOMASI endpoint not configured (set AIOTOMASI_API{1,2,3} + AIOTOMASI_APIKEY{1,2,3})'})}\n\n"
                return
            model = _chain[0][0]

            # Signal start
            yield f"event: thinking\ndata: {_json.dumps({'token': f'[Starting generation with {model}...]', 'stage': 'start'})}\n\n"

            # ── Stream from AI API (priority 1→2→3, each its own endpoint+key) ──
            resp, model = route_generate_call(
                json={
                    "messages": messages,
                    "stream": True,
                    "max_tokens": 120000,
                    "temperature": 0.7,
                    "reasoning": {"effort": "high"},
                },
                stream=True,
                timeout=1800,
            )
            resp.raise_for_status()

            # Stream tokens with heartbeat to prevent proxy timeout
            full_content = ""
            reasoning_acc = ""
            token_count = 0
            t_start = _time.time()
            t_last_yield = _time.time()

            # ── Live stream snapshot to Redis ─────────────────────────
            # Mirror the chat pattern: write reasoning+content incrementally
            # so a refresh/disconnect can read HOW FAR the backend has gotten
            # (read by GET /api/papers/<id>/generate-status). Throttled ~1.5s.
            _pf_stream_key = f"paperfull:stream:{paper_id}"
            _pf_started_at = datetime.now(timezone.utc).isoformat()
            _pf_last_write = [0.0]

            def _pf_snapshot(status, reasoning, content, error=None, force=False):
                now = _time.time()
                if not force and (now - _pf_last_write[0]) < 1.5:
                    return
                _pf_last_write[0] = now
                try:
                    _r = get_redis()
                    if _r:
                        _r.setex(_pf_stream_key, 1800, _json.dumps({
                            "status": status,
                            "reasoning": (reasoning or "")[-20000:],
                            "content": (content or "")[-60000:],
                            "started_at": _pf_started_at,
                            "error": error,
                        }, default=str))
                except Exception:
                    pass

            _pf_snapshot("streaming", reasoning_acc, full_content, force=True)


            try:
                for line in resp.iter_lines(decode_unicode=True):
                    # Heartbeat every 15s — prevents nginx/proxy idle timeout
                    if _time.time() - t_last_yield > 15:
                        yield f": heartbeat {_time.time()}\n\n"
                        t_last_yield = _time.time()
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = _json.loads(data_str)
                            delta = chunk.get("choices") or [{}]
                            if not delta:
                                continue
                            delta = delta[0].get("delta", {})

                            # Check for reasoning_content (some models emit this)
                            reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                            if reasoning:
                                reasoning_acc += reasoning
                                yield f"event: thinking\ndata: {_json.dumps({'token': reasoning})}\n\n"
                                t_last_yield = _time.time()
                                _pf_snapshot("streaming", reasoning_acc, full_content)

                            content = delta.get("content")
                            if content:
                                full_content += content
                                token_count += 1
                                yield f"event: content\ndata: {_json.dumps({'token': content, 'total_tokens': token_count})}\n\n"
                                t_last_yield = _time.time()
                                _pf_snapshot("streaming", reasoning_acc, full_content)
                        except _json.JSONDecodeError:
                            pass
                    elif line.startswith("{"):
                        try:
                            full = _json.loads(line)
                            choices = full.get("choices") or []
                            if choices:
                                msg = choices[0].get("message", {})
                                if msg.get("content"):
                                    full_content += msg["content"]
                                    yield f"event: content\ndata: {_json.dumps({'token': msg['content'], 'total_tokens': token_count})}\n\n"
                        except _json.JSONDecodeError:
                            pass
            except GeneratorExit:
                # Client disconnected — continue generation in background
                # so results are saved to DB even if the user navigates away.
                log.info("Client disconnected during generate-stream for paper %s, continuing in background", paper_id)
                try:
                    # Continue reading the remaining stream
                    for line in resp.iter_lines(decode_unicode=True):
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                chunk = _json.loads(data_str)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content")
                                if content:
                                    full_content += content
                                    _pf_snapshot("streaming", reasoning_acc, full_content)
                            except _json.JSONDecodeError:
                                pass
                        elif line.startswith("{"):
                            try:
                                full = _json.loads(line)
                                if full.get("choices"):
                                    msg = full["choices"][0].get("message", {})
                                    if msg.get("content"):
                                        full_content += msg["content"]
                            except _json.JSONDecodeError:
                                pass
                except Exception:
                    pass  # Best-effort — don't crash the background continuation
                finally:
                    resp.close()
                    resp = None
                # Try to parse and save even if incomplete
                # Wrap in app_context since Flask may have torn down on GeneratorExit
                try:
                    from flask import current_app
                    _bg_app = current_app._get_current_object()
                except Exception:
                    _bg_app = None
                _bg_ctx = _bg_app.app_context() if _bg_app else None
                if _bg_ctx:
                    _bg_ctx.__enter__()
                try:
                    if full_content:
                        import re as _re2
                        clean2 = _re2.sub(r"^```(?:json)?\s*", "", full_content.strip(), flags=_re2.IGNORECASE)
                        clean2 = _re2.sub(r"\s*```$", "", clean2)
                        try:
                            raw2 = _json.loads(clean2)
                        except _json.JSONDecodeError:
                            try:
                                from json_repair import repair_json as _rj
                                raw2 = _rj(clean2, return_objects=True)
                                if not isinstance(raw2, dict):
                                    raw2 = None
                            except Exception:
                                raw2 = None
                        if raw2 and isinstance(raw2, dict):
                            from tools.editor.single import _normalize_paper_shape as _nps
                            pd2 = _nps(raw2)
                            ok_bg, err_bg = _persist_paper_data(paper_id, user_id, pd2)
                            if ok_bg:
                                _update_bell_job("done", 100)
                                _pf_snapshot("done", reasoning_acc, full_content, force=True)
                                log.info("Background save completed for paper %s after client disconnect", paper_id)
                            else:
                                _update_bell_job("error", 100, error="Background save failed")
                                _pf_snapshot("error", reasoning_acc, full_content, error="Background save failed", force=True)
                                log.warning("Background save failed for paper %s: %s", paper_id, err_bg)
                        else:
                            _update_bell_job("error", 100, error="Background save: no parseable content")
                            _pf_snapshot("error", reasoning_acc, full_content, error="no parseable content", force=True)
                except Exception as e_bg:
                    _update_bell_job("error", 100, error=f"Background save failed: {e_bg}")
                    _pf_snapshot("error", reasoning_acc, full_content, error=str(e_bg), force=True)
                    log.warning("Background save failed for paper %s: %s", paper_id, e_bg)
                finally:
                    if _bg_ctx:
                        try:
                            _bg_ctx.__exit__(None, None, None)
                        except Exception:
                            pass
                return
            finally:
                if resp:
                    try:
                        resp.close()
                    except Exception:
                        pass

            elapsed = round(_time.time() - t_start, 1)

            if not full_content:
                _update_bell_job("error", 100, error="AI returned empty content")
                _pf_snapshot("error", reasoning_acc, full_content, error="AI returned empty content", force=True)
                yield f"event: error\ndata: {_json.dumps({'error': 'AI returned empty content'})}\n\n"
                return

            # ── Parse JSON response ───────────────────────────────────
            import re as _re
            try:
                from json_repair import repair_json
            except ImportError:
                repair_json = None

            clean = _re.sub(r"^```(?:json)?\s*", "", full_content.strip(), flags=_re.IGNORECASE)
            clean = _re.sub(r"\s*```$", "", clean)

            # Strip AI-injected error markers and corrupted trailing text
            _err_markers = ["[ERROR]", "[FATAL]", "[CRITICAL]"]
            for _marker in _err_markers:
                _idx = clean.find(_marker)
                if _idx > 0:
                    clean = clean[:_idx].rstrip()

            # Fix JSON keys with embedded newlines (AI corruption: "s\ne\nc\nt\ni\no\nn3" → "section3")
            def _fix_newline_keys(raw_str):
                """Remove ALL newlines inside quoted JSON keys (loops until clean).
                Fixes AI corruption: multi-byte splits like "s\ne\nc\nt\ni\no\nn3" -> "section3"
                """
                import re as _rfix
                _pat = _rfix.compile(r'"([^"]*?)\s*\n\s*([^"]*?)":')
                prev = None
                cur = raw_str
                while cur != prev:
                    prev = cur
                    cur = _pat.sub(lambda m: '"' + m.group(1).replace('\n', '').replace(' ', '') + m.group(2).replace('\n', '').replace(' ', '') + '":', cur)
                return cur
            clean = _fix_newline_keys(clean)
            try:
                raw_paper = _json.loads(clean)
            except _json.JSONDecodeError:
                if repair_json:
                    try:
                        raw_paper = repair_json(clean, return_objects=True)
                        if not isinstance(raw_paper, dict):
                            raise ValueError(f"json_repair returned {type(raw_paper)}")
                    except Exception as e2:
                        log.warning("JSON parse failed for paper %s: %s", paper_id, e2)
                        _update_bell_job("error", 100, error="JSON parse failed — paper content could not be parsed")
                        _pf_snapshot("error", reasoning_acc, full_content, error="JSON parse failed", force=True)
                        yield f"event: error\ndata: {_json.dumps({'error': 'JSON parse failed — paper content could not be parsed'})}\n\n"
                        return
                else:
                    _update_bell_job("error", 100, error="JSON parse failed and json_repair not available")
                    _pf_snapshot("error", reasoning_acc, full_content, error="JSON parse failed and json_repair not available", force=True)
                    yield f"event: error\ndata: {_json.dumps({'error': 'JSON parse failed and json_repair not available'})}\n\n"
                    return

            # ── Normalize paper shape ───────────────────────────────
            from tools.editor.single import _normalize_paper_shape
            paper_data = _normalize_paper_shape(raw_paper)

            # Inject resolved language so it persists in paper.data after save.
            # _normalize_paper_shape doesn't include language in its output,
            # so without this the chat backend can't read the paper's language.
            if _lang:
                paper_data["language"] = _lang

            # ── Post-process: fix mojibake + clean LaTeX artifacts ────
            from tools.paperfull.text_cleaner import clean_paper_data
            paper_data = clean_paper_data(paper_data)

            # ── Post-process: programmatic humanization (anti-Turnitin) ────
            try:
                from tools.humanizer.humanizer import TextHumanizer
                _humanizer = TextHumanizer()
                
                _HUMANIZER_SKIP_KEYS = {
                    'doi', 'url', 'year', 'volume', 'issue', 'pages',
                    'email', 'affiliation', 'institution', 'city',
                    'country', 'location', 'index', 'type', 'format',
                    'file', 'caption_ref', 'source',
                }
                
                def _humanize_text_val(text):
                    if not isinstance(text, str) or not text.strip():
                        return text
                    return _humanizer.humanize_program(text, option="Standard", intensity="medium")
                
                def _humanize_recursive(data):
                    if isinstance(data, dict):
                        return {k: (v if k in _HUMANIZER_SKIP_KEYS else _humanize_recursive(v))
                                for k, v in data.items()}
                    elif isinstance(data, list):
                        return [_humanize_recursive(item) for item in data]
                    elif isinstance(data, str):
                        if len(data.split()) > 20:
                            return _humanize_text_val(data)
                        return data
                    return data
                
                paper_data = _humanize_recursive(paper_data)
                log.info("[paperfull] Applied post-generation humanization (programmatic, anti-Turnitin)")
            except ImportError:
                log.info("[paperfull] Humanizer not available, skipping post-humanization")
            except Exception as _hum_e:
                log.warning("[paperfull] Post-humanization failed, continuing: %s", _hum_e)

            # ── Post-process: data integrity verification ────
            _stored_data_texts = paper_data.get("_data_texts", []) or []
            if _stored_data_texts:
                try:
                    _verify_result = _verify_data_integrity(paper_data, _stored_data_texts, paper_id)
                    if _verify_result:
                        paper_data["_data_warnings"] = _verify_result
                        log.warning("[paperfull] ⚠ Data integrity issues found for paper %s: %d warnings",
                                   paper_id, len(_verify_result))
                except Exception as _dv_e:
                    log.warning("[paperfull] Data verification failed: %s", _dv_e)

            # ── Inject data_texts for chart generation ──────────────
            # Priority: closure var → paper_data from LLM → pre-stored in Paper.data
            _injected_data_texts = data_texts or paper_data.get("_data_texts", []) or []
            if not _injected_data_texts:
                # Third fallback: read from pre-stored paper.data in DB
                try:
                    _stored = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
                    if _stored and _stored.data:
                        _stored_dict = _stored.data if isinstance(_stored.data, dict) else (
                            json.loads(_stored.data) if isinstance(_stored.data, str) else {}
                        )
                        _injected_data_texts = _stored_dict.get("_data_texts", []) or []
                        if _injected_data_texts:
                            log.info("[paperfull] Recovered %d data_texts from pre-stored paper.data",
                                     len(_injected_data_texts))
                except Exception as _rec_e:
                    log.warning("[paperfull] Failed to recover data_texts from DB: %s", _rec_e)
            if _injected_data_texts:
                paper_data["_data_texts"] = _injected_data_texts
                paper_data["_data_files_count"] = len([t for t in _injected_data_texts if t and t.strip()])

            # ── Save to DB (fresh connection, retries on stale SSL) ───
            try:
                ok, save_err = _persist_paper_data(paper_id, user_id, paper_data)
            except RuntimeError as _ctx_err:
                # May fail if working outside of application context
                log.warning("_persist_paper_data failed outside app context: %s", _ctx_err)
                from flask import current_app
                with current_app.app_context():
                    ok, save_err = _persist_paper_data(paper_id, user_id, paper_data)
            if not ok:
                _update_bell_job("error", 100, error=f"DB save failed: {save_err}")
                _pf_snapshot("error", reasoning_acc, full_content, error=f"DB save failed: {save_err}", force=True)
                yield f"event: error\ndata: {_json.dumps({'error': f'DB save failed: {save_err}'})}\n\n"
                return

            # ── Token deduction for Generate Full stream path ───────────────
            try:
                from utils.ai_tools.tools_api import _log_tool_usage
                _prompt_text = system_prompt + "\n" + user_message
                _prompt_tokens = max(1, len(_prompt_text) // 4)
                _completion_tokens = max(1, len(full_content or _json.dumps(paper_data, ensure_ascii=False)) // 4)
                # Generate Full is expensive in real provider usage (reasoning + long JSON),
                # while streaming often does not return exact usage. Charge a safe floor.
                _min_total_tokens = 120_000
                _completion_tokens += max(0, _min_total_tokens - (_prompt_tokens + _completion_tokens))
                _log_tool_usage(
                    int(user_id),
                    "generate-full",
                    model or "VIOLA-GENERATE",
                    _prompt_tokens,
                    _completion_tokens,
                )
                log.info(
                    "GENERATE_FULL_TOKEN_DEDUCT user=%s paper=%s model=%s prompt=%d completion=%d total=%d",
                    user_id, paper_id, model or "VIOLA-GENERATE", _prompt_tokens, _completion_tokens,
                    _prompt_tokens + _completion_tokens,
                )
            except Exception as _tok_e:
                log.warning("GENERATE_FULL_TOKEN_DEDUCT_FAILED user=%s paper=%s: %s", user_id, paper_id, _tok_e)

            # ── Auto-enqueue image generation jobs (section 2/3 conceptual) ──
            image_job_ids = []
            if generate_images:
                try:
                    image_prompts = _collect_gambar_prompts(paper_data, paper_kind=paper_kind)
                    if image_prompts:
                        from tools.image_generation.worker import submit_now as _img_submit
                        for idx, item in enumerate(image_prompts):
                            prompt_text = item["prompt"] if isinstance(item, dict) else item
                            # Derive target_path from gambar metadata for meaningful filename
                            target_path = None
                            if isinstance(item, dict):
                                img_num = item.get("image_number", "")
                                title = item.get("title", "")
                                orig_path = item.get("original_path", "")
                                section = item.get("_section", "")
                                # Try to extract filename from original path (e.g., "gambar/fig1.png" → "fig1")
                                if orig_path:
                                    import os, re as _re
                                    base = os.path.splitext(os.path.basename(orig_path))[0]
                                    base = _re.sub(r'[^A-Za-z0-9_.-]', '_', base)
                                    if base and base != "image":
                                        target_path = base + ".jpg"
                                if not target_path and img_num:
                                    target_path = f"fig{img_num}.jpg"
                                if not target_path and title:
                                    # Slugify title for filename
                                    slug = _re.sub(r'[^a-z0-9]+', '_', title.lower().strip())[:50].strip('_')
                                    if slug:
                                        target_path = f"fig{img_num}_{slug}.jpg" if img_num else f"{slug}.jpg"
                                # Fallback: use section + index
                                if not target_path:
                                    sec_num = section.replace("section", "") if section else ""
                                    prefix = f"sec{sec_num}" if sec_num else "fig"
                                    target_path = f"{prefix}_{idx+1}.jpg"

                            img_job = ImageGenJob(
                                id=uuid.uuid4().hex,
                                user_id=user_id,
                                paper_id=paper_id,
                                prompt=prompt_text[:2000],
                                status="queued",
                                target_path=target_path[:500] if target_path else None,
                            )
                            db.session.add(img_job)
                            image_job_ids.append(img_job.id)
                        safe_commit()
                        for jid in image_job_ids:
                            try:
                                _img_submit(jid)
                            except Exception:
                                pass  # dispatcher poll will pick it up
                        log.info("Auto-enqueued %d image jobs (all sections) for paper %s", len(image_job_ids), paper_id)
                except Exception as e_img:
                    db.session.rollback()
                    log.warning("Auto-image-gen failed for paper %s: %s", paper_id, e_img)

            # ── Send done event FIRST (JSON parsed to editor) ───────────
            # User sees paper content immediately. Images generate in background.
            _update_bell_job("done", 100)
            _pf_snapshot("done", reasoning_acc, full_content, force=True)
            yield f"event: done\ndata: {_json.dumps({'paper': paper_data, 'elapsed': elapsed, 'tokens': token_count, 'image_jobs': image_job_ids, 'total_jobs': len(image_job_ids) , 'images_pending': generate_images and (bool(image_job_ids) )})}\n\n"

            # ── Wait for ALL image jobs in background ─────────────────────
            # Continue SSE stream to send progress updates while images generate.
            # Frontend shows separate image progress panel.
            _all_job_ids = [jid for jid in image_job_ids if jid]

            if _all_job_ids:
                _total_jobs = len(_all_job_ids)
                yield f"event: progress\ndata: {_json.dumps({'stage': 'image_generation', 'message': f'Generating {_total_jobs} images...', 'total': _total_jobs, 'done': 0})}\n\n"
                log.info("[paperfull] Waiting for %d image/chart jobs for paper %s", _total_jobs, paper_id)

                _wait_start = _time.time()
                _max_wait = 120  # 2 minutes max — remaining images reconciled async
                _last_progress_emit = -10  # emit immediately on first check

                while True:
                    _elapsed_wait = _time.time() - _wait_start
                    if _elapsed_wait > _max_wait:
                        log.warning("[paperfull] Image wait timed out after %.0fs for paper %s", _elapsed_wait, paper_id)
                        yield f"event: progress\ndata: {_json.dumps({'stage': 'image_generation', 'message': 'Image generation timed out — some images may be missing', 'total': _total_jobs, 'done': _total_jobs})}\n\n"
                        break

                    try:
                        # Check ImageGenJob (Gemini) statuses
                        _img_done = 0
                        _img_errors = 0
                        for _jid in image_job_ids:
                            _img = ImageGenJob.query.get(_jid)
                            if _img:
                                if _img.status == "done":
                                    _img_done += 1
                                elif _img.status in ("error", "failed"):
                                    _img_done += 1
                                    _img_errors += 1

                        _all_done = _img_done
                        _pending = _total_jobs - _all_done

                        # Emit progress every 3 seconds at most
                        if _time.time() - _last_progress_emit > 3:
                            msg_parts = [f'Generating images: {_all_done}/{_total_jobs} done']
                            if _img_errors > 0:
                                msg_parts.append(f'({_img_errors} errors)')
                            yield f"event: progress\ndata: {_json.dumps({'stage': 'image_generation', 'message': ' '.join(msg_parts), 'total': _total_jobs, 'done': _all_done, 'errors': _img_errors})}\n\n"
                            _last_progress_emit = _time.time()

                        if _pending <= 0:
                            final_msg = f'All {_total_jobs} images generated!' if _img_errors == 0 else f'{_total_jobs - _img_errors}/{_total_jobs} images generated ({_img_errors} errors)'
                            log.info("[paperfull] All %d image/chart jobs completed in %.1fs for paper %s (%d errors)", _total_jobs, _elapsed_wait, paper_id, _img_errors)
                            yield f"event: progress\ndata: {_json.dumps({'stage': 'image_generation', 'message': final_msg, 'total': _total_jobs, 'done': _total_jobs, 'errors': _img_errors})}\n\n"
                            break
                    except Exception as _wait_e:
                        log.warning("[paperfull] Image wait poll error: %s", _wait_e)
                        try:
                            db.session.rollback()
                        except Exception:
                            pass

                    _time.sleep(3)

            # ── Launch background image reconciliation (daemon thread) ───────────
            # This runs even if GeneratorExit fires (client disconnects).
            # Reconciliation is I/O bound (DB + filesystem) so a daemon thread is fine.
            def _bg_reconcile():
                try:
                    from flask import current_app
                    with current_app.app_context():
                        from tools.image_generation.reconcile import reconcile_figure_images
                        from utils.core.storage_helper import get_user_dir
                        _upload_base = get_user_dir(int(user_id), "uploads")
                        reconcile_figure_images(paper_id, paper_data, _upload_base)
                        # Collect resolved paths from figures to prevent double-assignment
                        _used_by_figures: set[str] = set()
                        for fig in paper_data.get("figures", []):
                            if isinstance(fig, dict):
                                p = str(fig.get("Path") or fig.get("path") or "")
                                if p and os.path.isabs(p) and os.path.exists(p):
                                    _used_by_figures.add(p)
                        # Also walk sections for gambar items (not just top-level figures)
                        _reconcile_section_images(paper_data, paper_id, _upload_base)
                        # Re-save updated paper_data with resolved image paths
                        ok_rec, rec_err = _persist_paper_data(paper_id, user_id, paper_data)
                        if not ok_rec:
                            log.warning("[paperfull] Image reconciliation re-save failed for paper %s: %s", paper_id, rec_err)
                        log.info("[paperfull] Background image reconciliation complete for paper %s", paper_id)
                except Exception as _bg_e:
                    log.warning("[paperfull] Background image reconciliation failed for paper %s: %s", paper_id, _bg_e)

            _reconcile_thread = threading.Thread(target=_bg_reconcile, daemon=True)
            _reconcile_thread.start()

            # ── Count errors for images_complete event ────────────────────────
            error_count = 0
            if generate_images:
                try:
                    for _jid in image_job_ids:
                        _img = ImageGenJob.query.get(_jid)
                        if _img and _img.status in ("error", "failed"):
                            error_count += 1
                except Exception:
                    pass

            # ── Send images_complete event ─────────────────────────────
            yield f"event: images_complete\ndata: {_json.dumps({'image_jobs': image_job_ids, 'errors': error_count, 'total': len(image_job_ids) })}\n\n"

        except GeneratorExit:
            # Client disconnected before SSE finished. Do NOT try to write to
            # the response stream (yields RuntimeError). Just ensure any
            # in-flight DB state is cleaned up.
            log.warning("[paperfull] GeneratorExit: client disconnected before SSE completed for paper %s. "
                        "Image reconciliation may have been skipped.", paper_id)
            # Best-effort: snapshot whatever we accumulated so the user doesn't lose everything.
            try:
                _pf_snapshot("error", reasoning_acc, full_content,
                             error="client disconnected during streaming", force=True)
            except Exception:
                pass
            try:
                _update_bell_job("error", 100, error="client disconnected")
            except Exception:
                pass
            raise
        except Exception as e:
            import traceback
            tb = traceback.format_exc(limit=2)
            _update_bell_job("error", 100, error="Internal server error")
            try:
                _pf_snapshot("error", reasoning_acc, full_content, error="Internal server error", force=True)
            except Exception:
                pass
            log.exception("[paperfull] SSE stream error: %s", e)
            yield f"event: error\ndata: {_json.dumps({'error': 'Internal server error'})}\n\n"

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return Response(stream_with_context(gen()), headers=headers)
