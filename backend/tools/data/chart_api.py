"""Chart generation blueprint — v2.

Wires chart_generator into Flask endpoints for Section 4 (Results).
Supports 15+ chart types, styling options, color palettes, and preview.

Endpoints:
    GET    /api/papers/<paper_id>/charts              — list charts
    GET    /api/papers/<paper_id>/charts/<chart_id>   — get chart
    POST   /api/papers/<paper_id>/charts              — create chart
    PUT    /api/papers/<paper_id>/charts/<chart_id>   — update chart
    DELETE /api/papers/<paper_id>/charts/<chart_id>   — delete chart
    POST   /api/papers/<paper_id>/charts/preview      — preview (base64, no save)
    POST   /api/papers/<paper_id>/charts/upload-data  — upload data file
    GET    /api/papers/<paper_id>/charts/kinds        — list available chart types
    GET    /api/papers/<paper_id>/charts/palettes     — list color palettes
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from werkzeug.utils import secure_filename

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from tools.data.chart_generator import (
    ChartSpec, generate_chart, render_chart_base64,
    parse_data_file, CHART_KINDS, COLOR_PALETTES,
)
from database.models import Paper, PaperImage, db, safe_commit
from tools.editor.utils import safe_paper_dir, PAPER_ID_RE

log = logging.getLogger(__name__)

chart_api = Blueprint("chart_api", __name__)

ALLOWED_KINDS = set(CHART_KINDS.keys())


def _err(msg: str, code: str, status: int = 400):
    return jsonify({"error": msg, "code": code}), status


def _build_spec(data: dict) -> ChartSpec:
    """Build ChartSpec from request JSON, including styling options."""
    figsize_raw = data.get("figsize", (8, 5))
    figsize = (min(max(float(figsize_raw[0]), 2), 20), min(max(float(figsize_raw[1]), 2), 20))
    dpi = min(max(int(data.get("dpi", 150)), 50), 300)
    return ChartSpec(
        kind=data.get("kind", "line"),
        title=data.get("title", ""),
        xlabel=data.get("xlabel", ""),
        ylabel=data.get("ylabel", ""),
        data=data.get("data", []),
        series_labels=data.get("series_labels", []),
        x_data=data.get("x_data"),
        figsize=figsize,
        dpi=dpi,
        color_palette=data.get("color_palette", "academic"),
        custom_colors=data.get("custom_colors"),
        theme=data.get("theme", "clean"),
        font_size=data.get("font_size", 11),
        title_font_size=data.get("title_font_size", 14),
        show_grid=data.get("show_grid", True),
        show_legend=data.get("show_legend", True),
        legend_position=data.get("legend_position", "best"),
        annotations=data.get("annotations"),
        bar_width=data.get("bar_width", 0.8),
        line_width=data.get("line_width", 2.0),
        marker_size=data.get("marker_size", 6.0),
        show_data_labels=data.get("show_data_labels", False),
        rotation_x=data.get("rotation_x", 0),
    )


@chart_api.route("/api/papers/<paper_id>/charts/kinds", methods=["GET"])
@jwt_required()
def list_chart_kinds(paper_id: str):
    """Return available chart types with labels, icons, categories."""
    return jsonify({"kinds": CHART_KINDS}), 200


@chart_api.route("/api/papers/<paper_id>/charts/palettes", methods=["GET"])
@jwt_required()
def list_color_palettes(paper_id: str):
    """Return available color palettes."""
    return jsonify({"palettes": COLOR_PALETTES}), 200


@chart_api.route("/api/papers/<paper_id>/charts", methods=["GET"])
@jwt_required()
def list_charts(paper_id: str):
    if not PAPER_ID_RE.match(paper_id):
        return _err("Invalid paper id", "BAD_REQUEST", 400)
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return _err("Unauthorized", "UNAUTHORIZED", 401)

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return _err("Paper not found", "NOT_FOUND", 404)

    charts = PaperImage.query.filter(
        PaperImage.paper_id == paper_id,
        PaperImage.original_name.like("chart-%")
    ).order_by(PaperImage.created_at.desc()).all()

    return jsonify({
        "charts": [
            {
                **img.to_dict(),
                "kind": img.original_name.split("-")[1] if "-" in img.original_name else "unknown"
            }
            for img in charts
        ]
    }), 200


@chart_api.route("/api/papers/<paper_id>/charts/<int:chart_id>", methods=["GET"])
@jwt_required()
def get_chart(paper_id: str, chart_id: int):
    if not PAPER_ID_RE.match(paper_id):
        return _err("Invalid paper id", "BAD_REQUEST", 400)
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return _err("Unauthorized", "UNAUTHORIZED", 401)

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return _err("Paper not found", "NOT_FOUND", 404)

    chart = PaperImage.query.filter_by(id=chart_id, paper_id=paper_id).first()
    if not chart or not chart.original_name.startswith("chart-"):
        return _err("Chart not found", "NOT_FOUND", 404)

    return jsonify({
        **chart.to_dict(),
        "kind": chart.original_name.split("-")[1] if "-" in chart.original_name else "unknown"
    }), 200


@chart_api.route("/api/papers/<paper_id>/charts", methods=["POST"])
@jwt_required()
def create_chart(paper_id: str):
    if not PAPER_ID_RE.match(paper_id):
        return _err("Invalid paper id", "BAD_REQUEST", 400)
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return _err("Unauthorized", "UNAUTHORIZED", 401)

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return _err("Paper not found", "NOT_FOUND", 404)

    data = request.get_json(silent=True) or {}
    kind = (data.get("kind") or "").strip().lower()
    if kind not in ALLOWED_KINDS:
        return _err(f"Invalid chart kind; must be one of {sorted(ALLOWED_KINDS)}", "BAD_KIND", 400)

    title = str(data.get("title", "")).strip()
    if not title:
        return _err("title is required", "BAD_SPEC", 400)

    series_labels = data.get("series_labels") or []
    if not isinstance(series_labels, list):
        return _err("series_labels must be a list", "BAD_SPEC", 400)

    payload = data.get("data")
    if not isinstance(payload, list) or len(payload) == 0:
        return _err("data must be a non-empty list", "BAD_SPEC", 400)

    x_data = data.get("x_data")
    if x_data is not None and not isinstance(x_data, list):
        return _err("x_data must be a list or null", "BAD_SPEC", 400)

    try:
        spec = _build_spec(data)
    except Exception as e:
        return _err(f"Invalid chart spec: {e}", "BAD_SPEC", 400)

    try:
        out_path = Path(generate_chart(paper_id, spec, user_id=user_id, judul_paper=paper.title))
    except ValueError as e:
        return _err(f"Invalid chart spec: {e}", "BAD_SPEC", 400)
    except Exception as e:
        log.exception("chart.generate failed paper=%s", paper_id)
        return _err(f"Chart generation failed: {e}", "GENERATE_ERROR", 500)

    paper_dir = safe_paper_dir(paper_id)
    if paper_dir is None:
        return _err("Invalid paper id", "BAD_REQUEST", 400)
    paper_dir.mkdir(parents=True, exist_ok=True)

    filename = out_path.name
    dest = paper_dir / filename
    try:
        shutil.move(str(out_path), str(dest))
    except Exception as e:
        log.exception("chart.move failed paper=%s src=%s dst=%s", paper_id, out_path, dest)
        return _err(f"Chart save failed: {e}", "SAVE_ERROR", 500)

    img = PaperImage(
        paper_id=paper_id,
        user_id=user_id,
        filename=filename,
        original_name=f"chart-{kind}-{filename}",
        file_path=f"{paper_id}/{filename}",
    )
    db.session.add(img)
    try:
        safe_commit()
    except Exception:
        db.session.rollback()
        raise

    return jsonify({
        "image_id": img.id,
        "filename": filename,
        "url": f"/api/images/{paper_id}/{filename}",
        "kind": kind,
    }), 201


@chart_api.route("/api/papers/<paper_id>/charts/preview", methods=["POST"])
@jwt_required()
def preview_chart(paper_id: str):
    """Generate a chart preview as base64 PNG without saving to DB."""
    if not PAPER_ID_RE.match(paper_id):
        return _err("Invalid paper id", "BAD_REQUEST", 400)
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return _err("Unauthorized", "UNAUTHORIZED", 401)

    data = request.get_json(silent=True) or {}
    kind = (data.get("kind") or "").strip().lower()
    if kind not in ALLOWED_KINDS:
        return _err(f"Invalid chart kind", "BAD_KIND", 400)

    payload = data.get("data")
    if not isinstance(payload, list) or len(payload) == 0:
        return _err("data must be a non-empty list", "BAD_SPEC", 400)

    try:
        spec = _build_spec(data)
        # Lower DPI for preview speed
        spec.dpi = min(spec.dpi, 100)
        spec.figsize = (7, 4)
    except Exception as e:
        return _err(f"Invalid chart spec: {e}", "BAD_SPEC", 400)

    try:
        b64 = render_chart_base64(spec)
    except ValueError as e:
        return _err(str(e), "BAD_SPEC", 400)
    except Exception as e:
        log.exception("chart.preview failed paper=%s", paper_id)
        return _err(f"Preview failed: {e}", "PREVIEW_ERROR", 500)

    return jsonify({"image": b64, "kind": kind}), 200


@chart_api.route("/api/papers/<paper_id>/charts/<int:chart_id>", methods=["PUT"])
@jwt_required()
def update_chart(paper_id: str, chart_id: int):
    if not PAPER_ID_RE.match(paper_id):
        return _err("Invalid paper id", "BAD_REQUEST", 400)
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return _err("Unauthorized", "UNAUTHORIZED", 401)

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return _err("Paper not found", "NOT_FOUND", 404)

    chart = PaperImage.query.filter_by(id=chart_id, paper_id=paper_id, user_id=user_id).first()
    if not chart or not chart.original_name.startswith("chart-"):
        return _err("Chart not found", "NOT_FOUND", 404)

    data = request.get_json(silent=True) or {}
    kind = (data.get("kind") or "").strip().lower()
    if kind not in ALLOWED_KINDS:
        return _err(f"Invalid chart kind", "BAD_KIND", 400)

    title = str(data.get("title", "")).strip()
    if not title:
        return _err("title is required", "BAD_SPEC", 400)

    payload = data.get("data")
    if not isinstance(payload, list) or len(payload) == 0:
        return _err("data must be a non-empty list", "BAD_SPEC", 400)

    try:
        spec = _build_spec(data)
    except Exception as e:
        return _err(f"Invalid chart spec: {e}", "BAD_SPEC", 400)

    try:
        out_path = Path(generate_chart(paper_id, spec, user_id=user_id, judul_paper=paper.title))
    except ValueError as e:
        return _err(f"Invalid chart spec: {e}", "BAD_SPEC", 400)
    except Exception as e:
        log.exception("chart.regenerate failed paper=%s chart=%s", paper_id, chart_id)
        return _err(f"Chart regeneration failed: {e}", "GENERATE_ERROR", 500)

    paper_dir = safe_paper_dir(paper_id)
    if paper_dir is None:
        return _err("Invalid paper id", "BAD_REQUEST", 400)

    old_file = paper_dir / chart.filename
    if old_file.exists():
        try:
            old_file.unlink()
        except Exception as e:
            log.warning("Failed to delete old chart file: %s", e)

    filename = out_path.name
    dest = paper_dir / filename
    try:
        shutil.move(str(out_path), str(dest))
    except Exception as e:
        log.exception("chart.move failed paper=%s src=%s dst=%s", paper_id, out_path, dest)
        return _err(f"Chart save failed: {e}", "SAVE_ERROR", 500)

    chart.filename = filename
    chart.original_name = f"chart-{kind}-{filename}"
    chart.file_path = f"{paper_id}/{filename}"
    safe_commit()

    return jsonify({
        "image_id": chart.id,
        "filename": filename,
        "url": f"/api/images/{paper_id}/{filename}",
        "kind": kind,
    }), 200


@chart_api.route("/api/papers/<paper_id>/charts/<int:chart_id>", methods=["DELETE"])
@jwt_required()
def delete_chart(paper_id: str, chart_id: int):
    if not PAPER_ID_RE.match(paper_id):
        return _err("Invalid paper id", "BAD_REQUEST", 400)
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return _err("Unauthorized", "UNAUTHORIZED", 401)

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return _err("Paper not found", "NOT_FOUND", 404)

    chart = PaperImage.query.filter_by(id=chart_id, paper_id=paper_id, user_id=user_id).first()
    if not chart or not chart.original_name.startswith("chart-"):
        return _err("Chart not found", "NOT_FOUND", 404)

    paper_dir = safe_paper_dir(paper_id)
    if paper_dir:
        chart_file = paper_dir / chart.filename
        if chart_file.exists():
            try:
                chart_file.unlink()
            except Exception as e:
                log.warning("Failed to delete chart file: %s", e)

    db.session.delete(chart)
    safe_commit()

    return jsonify({"message": "Chart deleted successfully"}), 200


@chart_api.route("/api/papers/<paper_id>/charts/ai-format", methods=["POST"])
@jwt_required()
def ai_format_data(paper_id: str):
    """
    Format data dengan AI: extract file → markdown → AI → tabel + rekomendasi grafik.

    Accepts:
    - File upload (multipart/form-data, field: "file")
    - OR raw text (JSON body: {"text": "..."})

    Returns structured JSON with tables, chart_recommendations, summary.
    """
    if not PAPER_ID_RE.match(paper_id):
        return _err("Invalid paper id", "BAD_REQUEST", 400)
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return _err("Unauthorized", "UNAUTHORIZED", 401)

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return _err("Paper not found", "NOT_FOUND", 404)

    from tools.data.dataFormating import format_data_with_ai, format_file_with_ai
    import tempfile

    # Mode 1: File upload
    if "file" in request.files:
        file = request.files["file"]
        if not file or not file.filename or file.filename == "":
            return _err("No file selected", "BAD_REQUEST", 400)

        filename = secure_filename(file.filename)
        if not filename:
            return _err("Invalid filename", "BAD_REQUEST", 400)

        # Save to temp file
        ext = Path(filename).suffix.lower()
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        try:
            result = format_file_with_ai(tmp_path, filename=filename)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return jsonify(result), 200

    # Mode 2: Raw text in JSON body
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return _err("Provide 'file' (upload) or 'text' (JSON body)", "BAD_REQUEST", 400)

    result = format_data_with_ai(text, filename=data.get("filename"))
    return jsonify(result), 200


@chart_api.route("/api/papers/<paper_id>/charts/upload-data", methods=["POST"])
@jwt_required()
def upload_chart_data(paper_id: str):
    if not PAPER_ID_RE.match(paper_id):
        return _err("Invalid paper id", "BAD_REQUEST", 400)
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return _err("Unauthorized", "UNAUTHORIZED", 401)

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return _err("Paper not found", "NOT_FOUND", 404)

    if "file" not in request.files:
        return _err("No file provided", "BAD_REQUEST", 400)

    file = request.files["file"]
    if not file or file.filename == "":
        return _err("No file selected", "BAD_REQUEST", 400)

    filename = secure_filename(file.filename)
    if not filename:
        return _err("Invalid filename", "BAD_REQUEST", 400)

    ext = Path(filename).suffix.lower()
    if ext not in [".csv", ".tsv", ".xlsx", ".xls", ".pdf", ".docx", ".doc"]:
        return _err(
            "Unsupported file type. Allowed: .csv, .tsv, .xlsx, .xls, .pdf, .docx, .doc",
            "BAD_FILE_TYPE", 400
        )

    paper_dir = safe_paper_dir(paper_id)
    if paper_dir is None:
        return _err("Invalid paper id", "BAD_REQUEST", 400)
    paper_dir.mkdir(parents=True, exist_ok=True)

    temp_filename = f"data-{uuid.uuid4().hex[:8]}{ext}"
    temp_path = paper_dir / temp_filename

    try:
        file.save(str(temp_path))
    except Exception as e:
        log.exception("Failed to save uploaded file paper=%s", paper_id)
        return _err(f"File save failed: {e}", "SAVE_ERROR", 500)

    try:
        parsed = parse_data_file(str(temp_path))
    except FileNotFoundError:
        return _err("File not found after upload", "INTERNAL_ERROR", 500)
    except ValueError as e:
        temp_path.unlink(missing_ok=True)
        return _err(f"Unsupported file format: {e}", "BAD_FILE_TYPE", 400)
    except RuntimeError as e:
        temp_path.unlink(missing_ok=True)
        return _err(str(e), "PARSE_ERROR", 500)
    except Exception as e:
        log.exception("Failed to parse data file paper=%s", paper_id)
        temp_path.unlink(missing_ok=True)
        return _err(f"File parsing failed: {e}", "PARSE_ERROR", 500)

    # Save to user storage data/ dir
    try:
        from utils.core.user_storage import get_username, save_data
        _uname = get_username(user_id=user_id)
        _judul = paper.title if paper else "untitled"
        save_data(_uname, _judul, str(temp_path), file.filename or temp_filename)
    except Exception:
        pass

    temp_path.unlink(missing_ok=True)

    return jsonify({
        "columns": parsed["columns"],
        "rows": parsed["rows"],
        "n_rows": parsed["n_rows"],
        "preview": parsed["preview"],
        "filename": filename
    }), 200
