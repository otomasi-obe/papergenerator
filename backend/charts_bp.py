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
from pathlib import Path

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from chart_generator import ChartSpec, generate_chart
from models import Paper, PaperImage, db
from paper_utils import PAPER_ID_RE, safe_paper_dir

log = logging.getLogger(__name__)

charts_bp = Blueprint("charts", __name__)

ALLOWED_KINDS = {"line", "bar", "scatter", "hist", "box", "heatmap", "pie"}


def _err(msg: str, code: str, status: int = 400):
    return jsonify({"error": msg, "code": code}), status


@charts_bp.route("/api/papers/<paper_id>/charts", methods=["POST"])
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
        out_path = Path(generate_chart(paper_id, spec))
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

    return jsonify({
        "image_id": img.id,
        "filename": filename,
        "url": f"/api/images/{paper_id}/{filename}",
        "kind": kind,
    }), 201
