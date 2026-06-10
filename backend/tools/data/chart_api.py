"""Chart generation blueprint — wires chart_generator into a Flask endpoint
so Section 4 (Results) can render matplotlib PNGs from user-supplied data.

POST /api/papers/<paper_id>/charts
    JSON body: { kind, title, xlabel, ylabel, data, series_labels?, x_data? }
    Generates a PNG via chart_generator.generate_chart(), moves it into the
    paper's data/uploads/ folder, registers a PaperImage row, and returns
    {image_id, filename, url} so the frontend can embed it in Section 4.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from werkzeug.utils import secure_filename

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from tools.data.chart_generator import ChartSpec, generate_chart, parse_data_file
from database.models import Paper, PaperImage, db
from tools.editor.utils import safe_paper_dir, PAPER_ID_RE

log = logging.getLogger(__name__)

chart_api = Blueprint("chart_api", __name__)

ALLOWED_KINDS = {"line", "bar", "scatter", "hist", "box", "heatmap", "pie"}


def _err(msg: str, code: str, status: int = 400):
    return jsonify({"error": msg, "code": code}), status


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

    chart = PaperImage.query.filter_by(
        id=chart_id,
        paper_id=paper_id
    ).first()
    
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
        try:

            user_id = int(get_jwt_identity())

        except (ValueError, TypeError):

            return jsonify({"error": "Invalid user identity"}), 401
    except (TypeError, ValueError):
        return _err("Unauthorized", "UNAUTHORIZED", 401)

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return _err("Paper not found", "NOT_FOUND", 404)

    data = request.get_json(silent=True) or {}
    kind = (data.get("kind") or "").strip().lower()
    if kind not in ALLOWED_KINDS:
        return _err(
            f"Invalid chart kind; must be one of {sorted(ALLOWED_KINDS)}",
            "BAD_KIND",
            400,
        )

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
        spec = ChartSpec(
            kind=kind,  # type: ignore[arg-type]
            title=title,
            xlabel=str(data.get("xlabel", "")),
            ylabel=str(data.get("ylabel", "")),
            data=payload,
            series_labels=[str(s) for s in series_labels],
            x_data=x_data,
        )
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
    db.session.commit()

    return (
        jsonify(
            {
                "image_id": img.id,
                "filename": filename,
                "url": f"/api/images/{paper_id}/{filename}",
                "kind": kind,
            }
        ),
        201,
    )


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

    chart = PaperImage.query.filter_by(
        id=chart_id,
        paper_id=paper_id,
        user_id=user_id
    ).first()
    
    if not chart or not chart.original_name.startswith("chart-"):
        return _err("Chart not found", "NOT_FOUND", 404)

    data = request.get_json(silent=True) or {}
    kind = (data.get("kind") or "").strip().lower()
    if kind not in ALLOWED_KINDS:
        return _err(
            f"Invalid chart kind; must be one of {sorted(ALLOWED_KINDS)}",
            "BAD_KIND",
            400,
        )

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
        spec = ChartSpec(
            kind=kind,  # type: ignore[arg-type]
            title=title,
            xlabel=str(data.get("xlabel", "")),
            ylabel=str(data.get("ylabel", "")),
            data=payload,
            series_labels=[str(s) for s in series_labels],
            x_data=x_data,
        )
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
    db.session.commit()

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

    chart = PaperImage.query.filter_by(
        id=chart_id,
        paper_id=paper_id,
        user_id=user_id
    ).first()
    
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
    db.session.commit()

    return jsonify({"message": "Chart deleted successfully"}), 200


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
            "BAD_FILE_TYPE",
            400
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
