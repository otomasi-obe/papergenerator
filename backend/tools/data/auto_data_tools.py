"""
Auto Data Tools Pipeline — generates charts from paperfull section 4 data_tools_payload.

After paperfull generates section 4 (Results), this module:
1. Parses `data_tools_payload` from figures and tables
2. Converts them to ChartSpec objects
3. Generates PNG charts via chart_generator
4. Updates figure entries with generated paths

Called from paper_worker.py after _auto_enqueue_figure_images().
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def _payload_to_chart_spec(payload: dict, paper_id: str) -> Optional[dict]:
    """Convert a data_tools_payload dict to a ChartSpec-compatible dict.

    Returns None if payload is invalid or missing required fields.
    """
    if not payload or not isinstance(payload, dict):
        return None

    kind = str(payload.get("kind") or "").strip().lower()
    if not kind:
        return None

    title = str(payload.get("title") or "Chart").strip()
    xlabel = str(payload.get("xlabel") or "").strip()
    ylabel = str(payload.get("ylabel") or "").strip()

    # Data can be: [[v1,v2,v3], [v4,v5,v6]] (series per row)
    # Or: [[categories], [series1], [series2]] (first row is categories)
    data = payload.get("data")
    if not data or not isinstance(data, list):
        return None

    # Validate data structure
    if len(data) < 1:
        return None

    series_labels = payload.get("series_labels") or []
    categories = payload.get("categories") or []
    color_palette = str(payload.get("color_palette") or "academic").strip()
    theme = str(payload.get("theme") or "clean").strip()

    # Handle different data formats
    # Format 1: data = [[series1_vals], [series2_vals]] with separate categories
    # Format 2: data = [[cats], [series1], [series2]] — first row is categories
    if categories and len(data) >= 1:
        # Categories provided separately
        chart_data = data
    elif len(data) >= 2 and isinstance(data[0][0], str):
        # First row looks like categories (strings)
        categories = data[0]
        chart_data = data[1:]
    else:
        chart_data = data

    # Ensure all numeric values are floats
    cleaned_data = []
    for row in chart_data:
        cleaned_row = []
        for val in row:
            if isinstance(val, (int, float)):
                cleaned_row.append(float(val))
            elif isinstance(val, str):
                try:
                    cleaned_row.append(float(val.replace("%", "").replace(",", "")))
                except (ValueError, AttributeError):
                    cleaned_row.append(0.0)
            else:
                cleaned_row.append(0.0)
        cleaned_data.append(cleaned_row)

    if not cleaned_data:
        return None

    return {
        "kind": kind,
        "title": title,
        "xlabel": xlabel,
        "ylabel": ylabel,
        "data": cleaned_data,
        "series_labels": series_labels,
        "categories": categories,
        "color_palette": color_palette,
        "theme": theme,
        "paper_id": paper_id,
    }


def _generate_chart_from_spec(spec_dict: dict, user_id: int, paper_id: str, judul: str, target_path: str = None) -> Optional[dict]:
    """Generate a chart PNG from a spec dict. Returns {path, filename, url} or None on error."""
    try:
        from tools.data.chart_generator import ChartSpec, generate_chart
        import shutil
        from pathlib import Path
        from tools.editor.utils import safe_paper_image_dir, safe_paper_dir

        spec = ChartSpec(
            kind=spec_dict["kind"],
            title=spec_dict["title"],
            xlabel=spec_dict.get("xlabel", ""),
            ylabel=spec_dict.get("ylabel", ""),
            data=spec_dict["data"],
            series_labels=spec_dict.get("series_labels", []),
            x_data=spec_dict.get("categories") or None,
            color_palette=spec_dict.get("color_palette", "academic"),
            theme=spec_dict.get("theme", "clean"),
        )

        out_path = Path(generate_chart(paper_id, spec, user_id=user_id, judul_paper=judul, target_path=target_path))
        log.info("[auto_data_tools] Generated chart: %s", out_path)

        # Move to paper image directory: user/<username>/<paper_id>/image/
        paper_dir = safe_paper_image_dir(paper_id)
        if paper_dir is None:
            log.warning("[auto_data_tools] Invalid paper_id: %s", paper_id)
            return None
        paper_dir.mkdir(parents=True, exist_ok=True)

        filename = out_path.name
        dest = paper_dir / filename
        shutil.move(str(out_path), str(dest))

        # Save to database as PaperImage with chart- prefix
        from database.models import PaperImage, db, safe_commit

        img = PaperImage(
            paper_id=paper_id,
            user_id=user_id,
            filename=filename,
            original_name=f"chart-auto-{spec.kind}-{filename}",
            file_path=f"{paper_id}/{filename}",
        )
        db.session.add(img)
        try:
            safe_commit()
        except Exception:
            db.session.rollback()
            log.warning("[auto_data_tools] Failed to save chart to DB", exc_info=True)
            return None

        url = f"/api/images/{paper_id}/{filename}"
        return {"path": str(dest), "filename": filename, "url": url, "image_id": img.id}

    except Exception as e:
        log.warning("[auto_data_tools] Failed to generate chart: %s", e)
        return None


def auto_generate_data_charts(
    paper_id: str,
    user_id: int,
    paper_data: dict,
) -> dict:
    """
    Auto-generate charts from data_tools_payload in paper_data.

    Walks:
    1. Top-level figures[] with data_tools_payload
    2. Top-level tables[] with data_tools_payload
    3. Section 4 nested content (section4a, section4b, etc.) — where LLM actually places gambar items

    Generates PNG charts via chart_generator and updates figure entries with generated paths.

    Returns: {charts_generated: int, errors: int}
    """
    import re
    from concurrent.futures import ThreadPoolExecutor, as_completed

    judul = paper_data.get("title") or "Paper"
    figures = paper_data.get("figures", [])
    tables = paper_data.get("tables", [])

    # Also collect gambar items from section 4 nested content
    section4_figures: list[dict] = []
    section4_tables: list[dict] = []

    def _walk_section4(obj, in_section4=False):
        """Walk paper_data and find gambar/tabel items in section 4 content."""
        if isinstance(obj, dict):
            if in_section4:
                if obj.get("id") == "gambar":
                    section4_figures.append(obj)
                elif obj.get("id") == "tabel" or obj.get("type") == "table":
                    section4_tables.append(obj)
            for k, v in obj.items():
                child_in_section4 = in_section4 or (isinstance(k, str) and bool(
                    re.match(r'section4[a-z]?$', k)
                ))
                _walk_section4(v, in_section4=child_in_section4)
        elif isinstance(obj, list):
            for item in obj:
                _walk_section4(item, in_section4=in_section4)

    _walk_section4(paper_data)

    # Collect all chart specs from figures and tables
    chart_tasks: List[Dict[str, Any]] = []

    # From top-level figures (section 4 grafik)
    for i, fig in enumerate(figures):
        payload = fig.get("data_tools_payload")
        if not payload:
            continue

        spec_dict = _payload_to_chart_spec(payload, paper_id)
        if spec_dict:
            chart_tasks.append({
                "spec": spec_dict,
                "type": "figure",
                "index": i,
                "title": fig.get("Title") or spec_dict["title"],
                "ref": fig,  # reference to update in paper_data
            })

    # From top-level tables (section 4 tabel with analysis + optional chart)
    for i, tbl in enumerate(tables):
        payload = tbl.get("data_tools_payload")
        if not payload:
            continue

        # Tables can have an embedded chart recommendation
        chart_payload = payload.get("chart")
        if chart_payload:
            spec_dict = _payload_to_chart_spec(chart_payload, paper_id)
            if spec_dict:
                chart_tasks.append({
                    "spec": spec_dict,
                    "type": "table_chart",
                    "index": i,
                    "title": spec_dict["title"],
                    "ref": tbl,
                })

    # From section 4 nested gambar items (where LLM actually puts them)
    for i, fig in enumerate(section4_figures):
        payload = fig.get("data_tools_payload") or fig.get("data_tools")
        if not payload:
            continue

        spec_dict = _payload_to_chart_spec(payload, paper_id)
        if spec_dict:
            chart_tasks.append({
                "spec": spec_dict,
                "type": "section4_figure",
                "index": i,
                "title": fig.get("Title") or spec_dict["title"],
                "ref": fig,
            })

    if not chart_tasks:
        log.info("[auto_data_tools] No data_tools_payload found in paper_data for paper_id=%s", paper_id)
        return {"charts_generated": 0, "errors": 0}

    log.info("[auto_data_tools] Found %d chart tasks for paper_id=%s (top=%d figures, %d tables; sec4=%d nested)",
             len(chart_tasks), paper_id, len(figures), len(tables), len(section4_figures))

    # Generate charts in parallel (max 4 workers)
    results = {"charts_generated": 0, "errors": 0}

    def _gen_one(task: dict) -> tuple:
        """Generate one chart, return (task, result_dict_or_none)."""
        spec_dict = task["spec"]
        result = _generate_chart_from_spec(spec_dict, user_id, paper_id, judul)
        return (task, result)

    max_workers = min(4, len(chart_tasks))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_gen_one, task): task for task in chart_tasks}
        for future in as_completed(futures):
            task, result = future.result()
            if result:
                results["charts_generated"] += 1

                # Update the figure/table entry with the generated path and url
                ref = task.get("ref")
                if ref and isinstance(ref, dict):
                    ref["generated_image_path"] = result["path"]
                    ref["generated_image_url"] = result["url"]
                    ref["image_source"] = "data_tools"
                    ref["image_id"] = result["image_id"]
            else:
                results["errors"] += 1

    log.info(
        "[auto_data_tools] Done: %d charts generated, %d errors for paper_id=%s",
        results["charts_generated"],
        results["errors"],
        paper_id,
    )

    return results


def auto_save_data_sources_to_db(
    paper_id: str,
    user_id: int,
    paper_data: dict,
) -> int:
    """
    Save tables from section 4 (with data_tools_payload) to paper_data.
    The tables are already in paper_data — no separate DB save needed.
    Returns: number of tables processed.
    """
    tables = paper_data.get("tables", [])
    count = 0
    for tbl in tables:
        if tbl.get("data_tools_payload"):
            count += 1
    return count
