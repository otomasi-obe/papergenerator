"""Chart generator for paper section 4 (Results).

Generates matplotlib PNG charts from user-provided or AI-estimated data.
Output saved to backend/data/charts/<paper_id>/<chart_id>.png.

Usage:
    from chart_generator import generate_chart, ChartSpec

    spec = ChartSpec(
        kind="line",  # line, bar, scatter, hist, box, heatmap, pie
        title="Energy consumption over time",
        xlabel="Time (s)",
        ylabel="Energy (mJ)",
        data=[[10, 12, 9, 15, 11]],
        series_labels=["Method A"],
    )
    out_path = generate_chart(paper_id, spec)
"""
import os
import logging
import uuid
from dataclasses import dataclass, field
from typing import Literal, Optional

log = logging.getLogger(__name__)

CHARTS_DIR = os.path.join(os.path.dirname(__file__), "data", "charts")
os.makedirs(CHARTS_DIR, exist_ok=True)


@dataclass
class ChartSpec:
    kind: Literal["line", "bar", "scatter", "hist", "box", "heatmap", "pie"]
    title: str
    xlabel: str = ""
    ylabel: str = ""
    data: list = field(default_factory=list)
    series_labels: list = field(default_factory=list)
    x_data: Optional[list] = None
    figsize: tuple = (8, 5)
    dpi: int = 120
    style: str = "seaborn-v0_8-whitegrid"


def generate_chart(paper_id: str, spec: ChartSpec) -> str:
    """Generate a chart PNG and return absolute path.

    Raises ValueError on invalid spec.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not spec.kind:
        raise ValueError("spec.kind is required")
    if spec.data is None or len(spec.data) == 0:
        raise ValueError("spec.data is required and must be non-empty")

    safe_paper_id = str(paper_id) if paper_id else "default"
    out_dir = os.path.join(CHARTS_DIR, safe_paper_id)
    os.makedirs(out_dir, exist_ok=True)

    chart_id = str(uuid.uuid4())[:8]
    out_path = os.path.join(out_dir, f"{chart_id}.png")

    try:
        plt.style.use(spec.style)
    except Exception:
        plt.style.use("default")

    fig, ax = plt.subplots(figsize=spec.figsize, dpi=spec.dpi)

    try:
        if spec.kind == "line":
            for i, ys in enumerate(spec.data):
                xs = spec.x_data if spec.x_data is not None else list(range(len(ys)))
                label = spec.series_labels[i] if i < len(spec.series_labels) else f"Series {i+1}"
                ax.plot(xs, ys, label=label, marker="o", linewidth=2)
            if spec.series_labels:
                ax.legend(loc="best", frameon=True)
        elif spec.kind == "bar":
            cats = spec.x_data or [f"C{i}" for i in range(len(spec.data[0]))]
            if len(spec.data) == 1:
                ax.bar(cats, spec.data[0])
            else:
                import numpy as np
                x = np.arange(len(cats))
                width = 0.8 / len(spec.data)
                for i, ys in enumerate(spec.data):
                    offset = (i - len(spec.data) / 2) * width + width / 2
                    label = spec.series_labels[i] if i < len(spec.series_labels) else f"Series {i+1}"
                    ax.bar(x + offset, ys, width, label=label)
                ax.set_xticks(x)
                ax.set_xticklabels(cats)
                if spec.series_labels:
                    ax.legend(loc="best", frameon=True)
        elif spec.kind == "scatter":
            if not spec.x_data or not spec.data:
                raise ValueError("scatter requires x_data and data")
            for i, ys in enumerate(spec.data):
                label = spec.series_labels[i] if i < len(spec.series_labels) else f"Series {i+1}"
                ax.scatter(spec.x_data, ys, label=label, alpha=0.7)
            if spec.series_labels:
                ax.legend(loc="best", frameon=True)
        elif spec.kind == "hist":
            for i, ys in enumerate(spec.data):
                label = spec.series_labels[i] if i < len(spec.series_labels) else f"Series {i+1}"
                ax.hist(ys, bins=20, alpha=0.6, label=label)
            if spec.series_labels:
                ax.legend(loc="best", frameon=True)
        elif spec.kind == "box":
            ax.boxplot(spec.data, labels=spec.series_labels or None)
        elif spec.kind == "heatmap":
            import numpy as np
            arr = np.array(spec.data)
            im = ax.imshow(arr, cmap="viridis", aspect="auto")
            plt.colorbar(im, ax=ax)
        elif spec.kind == "pie":
            if not spec.data or not spec.data[0]:
                raise ValueError("pie requires data[0] = list of values")
            labels = spec.series_labels or [f"S{i}" for i in range(len(spec.data[0]))]
            ax.pie(spec.data[0], labels=labels, autopct="%1.1f%%", startangle=90)
        else:
            raise ValueError(f"unknown chart kind: {spec.kind}")

        if spec.kind != "pie":
            ax.set_xlabel(spec.xlabel)
            ax.set_ylabel(spec.ylabel)
        ax.set_title(spec.title)

        plt.tight_layout()
        plt.savefig(out_path, bbox_inches="tight", dpi=spec.dpi)
    finally:
        plt.close(fig)

    log.info("chart generated: paper=%s kind=%s path=%s", safe_paper_id, spec.kind, out_path)
    return out_path


def parse_data_file(file_path: str) -> dict:
    """Parse CSV/TSV/Excel into a dict with columns and rows for AI analysis.

    Returns: {"columns": [...], "rows": [[...]], "n_rows": int, "preview": "..." }
    Raises ValueError for unsupported extensions, RuntimeError if openpyxl missing.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

    ext = os.path.splitext(file_path)[1].lower()
    if ext in [".csv", ".tsv"]:
        import csv
        sep = "\t" if ext == ".tsv" else ","
        with open(file_path, encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=sep)
            rows = list(reader)
        if not rows:
            return {"columns": [], "rows": [], "n_rows": 0, "preview": "(empty)"}
        cols = rows[0]
        data = rows[1:]
        return {
            "columns": cols,
            "rows": data[:50],
            "n_rows": len(data),
            "preview": "\n".join(["\t".join(r) for r in rows[:10]]),
        }
    elif ext in [".xlsx", ".xls"]:
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError("openpyxl not installed; cannot parse xlsx")
        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet = wb.active
        rows = [[cell.value for cell in r] for r in sheet.iter_rows()]
        if not rows:
            return {"columns": [], "rows": [], "n_rows": 0, "preview": "(empty)"}
        cols = rows[0]
        data = rows[1:]
        return {
            "columns": cols,
            "rows": data[:50],
            "n_rows": len(data),
            "preview": "\n".join(["\t".join("" if c is None else str(c) for c in r) for r in rows[:10]]),
        }
    else:
        raise ValueError(f"unsupported file ext: {ext}")
