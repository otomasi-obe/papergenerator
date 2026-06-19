"""Chart generator for paper section 4 (Results) — v2.

Generates publication-quality matplotlib PNG charts from user-provided or AI-estimated data.
Output saved to backend/data/charts/<paper_id>/<chart_id>.png.

Supports 15+ chart types with extensive styling options.

Usage:
    from chart_generator import generate_chart, ChartSpec, render_chart_base64

    spec = ChartSpec(
        kind="line",
        title="Energy consumption over time",
        xlabel="Time (s)",
        ylabel="Energy (mJ)",
        data=[[10, 12, 9, 15, 11]],
        series_labels=["Method A"],
    )
    out_path = generate_chart(paper_id, spec)
"""

import base64
import io
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Literal, Optional

log = logging.getLogger(__name__)

CHARTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "charts")
os.makedirs(CHARTS_DIR, exist_ok=True)

# ─── Chart type registry ──────────────────────────────────────────────
CHART_KINDS = {
    "line":          {"label": "Line Chart",        "icon": "📈", "category": "basic"},
    "bar":           {"label": "Bar Chart",         "icon": "📊", "category": "basic"},
    "scatter":       {"label": "Scatter Plot",      "icon": "⚬",  "category": "basic"},
    "pie":           {"label": "Pie Chart",         "icon": "🥧", "category": "basic"},
    "hist":          {"label": "Histogram",         "icon": "📊", "category": "basic"},
    "box":           {"label": "Box Plot",          "icon": "📦", "category": "basic"},
    "heatmap":       {"label": "Heatmap",           "icon": "🗺", "category": "basic"},
    "area":          {"label": "Area Chart",        "icon": "📈", "category": "advanced"},
    "stacked_bar":   {"label": "Stacked Bar",       "icon": "📊", "category": "advanced"},
    "stacked_area":  {"label": "Stacked Area",      "icon": "📈", "category": "advanced"},
    "donut":         {"label": "Donut Chart",       "icon": "🍩", "category": "advanced"},
    "hbar":          {"label": "Horizontal Bar",    "icon": "📊", "category": "advanced"},
    "radar":         {"label": "Radar / Polar",     "icon": "🕸", "category": "advanced"},
    "waterfall":     {"label": "Waterfall",         "icon": "💧", "category": "advanced"},
    "bubble":        {"label": "Bubble Chart",      "icon": "🫧", "category": "advanced"},
    "violin":        {"label": "Violin Plot",       "icon": "🎻", "category": "statistical"},
    "combo":         {"label": "Combo (Bar+Line)",  "icon": "📉", "category": "advanced"},
}

# ─── Color palettes ──────────────────────────────────────────────────
COLOR_PALETTES = {
    "academic":  ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#be185d", "#65a30d"],
    "vibrant":   ["#ef4444", "#3b82f6", "#22c55e", "#eab308", "#a855f7", "#ec4899", "#14b8a6", "#f97316"],
    "pastel":    ["#93c5fd", "#86efac", "#fca5a5", "#fde047", "#c4b5fd", "#f9a8d4", "#67e8f9", "#fdba74"],
    "monochrome":["#1e293b", "#475569", "#64748b", "#94a3b8", "#cbd5e1", "#334155", "#78716c", "#a8a29e"],
    "warm":      ["#dc2626", "#ea580c", "#d97706", "#ca8a04", "#f97316", "#ef4444", "#b91c1c", "#c2410c"],
    "cool":      ["#2563eb", "#0891b2", "#7c3aed", "#4f46e5", "#0d9488", "#2dd4bf", "#6366f1", "#8b5cf6"],
    "earth":     ["#92400e", "#166534", "#854d0e", "#1e3a5f", "#78350f", "#365314", "#7c2d12", "#134e4a"],
    "ocean":     ["#0c4a6e", "#0e7490", "#155e75", "#164e63", "#0369a1", "#0284c7", "#06b6d4", "#22d3ee"],
}

DEFAULT_PALETTE = "academic"

# ─── Matplotlib themes ───────────────────────────────────────────────
MPL_THEMES = {
    "clean":    "seaborn-v0_8-whitegrid",
    "minimal":  "seaborn-v0_8-white",
    "dark":     "seaborn-v0_8-darkgrid",
    "classic":  "classic",
    "default":  "default",
}


@dataclass
class ChartSpec:
    kind: str
    title: str
    xlabel: str = ""
    ylabel: str = ""
    data: list = field(default_factory=list)
    series_labels: list = field(default_factory=list)
    x_data: Optional[list] = None
    figsize: tuple = (8, 5)
    dpi: int = 150
    # Styling options
    color_palette: str = DEFAULT_PALETTE
    custom_colors: Optional[list] = None
    theme: str = "clean"
    font_size: int = 11
    title_font_size: int = 14
    show_grid: bool = True
    show_legend: bool = True
    legend_position: str = "best"
    annotations: Optional[dict] = None  # {index: "text"} for data labels
    bar_width: float = 0.8
    line_width: float = 2.0
    marker_size: float = 6.0
    show_data_labels: bool = False
    rotation_x: int = 0


def _get_colors(spec: ChartSpec, n: int) -> list:
    """Get n colors from the palette."""
    if spec.custom_colors and len(spec.custom_colors) >= n:
        return spec.custom_colors[:n]
    palette = COLOR_PALETTES.get(spec.color_palette, COLOR_PALETTES[DEFAULT_PALETTE])
    colors = []
    for i in range(n):
        colors.append(palette[i % len(palette)])
    return colors


def _apply_theme(spec):
    """Apply matplotlib theme (thread-safe, no global mutation)."""
    import matplotlib
    matplotlib.use("Agg")
    # Theme applied per-figure via style context in generate_chart/render_chart_base64


def _setup_axes(fig, ax, spec: ChartSpec, is_polar=False):
    """Common axis setup."""
    import matplotlib.pyplot as plt

    fs = spec.font_size
    ax.tick_params(axis='x', labelsize=fs - 1)
    ax.tick_params(axis='y', labelsize=fs - 1)

    if spec.title:
        ax.set_title(spec.title, fontweight='bold', pad=12, fontsize=spec.title_font_size)

    if not is_polar:
        if spec.xlabel:
            ax.set_xlabel(spec.xlabel, labelpad=8)
        if spec.ylabel:
            ax.set_ylabel(spec.ylabel, labelpad=8)
        ax.tick_params(axis='x', rotation=spec.rotation_x)

    if spec.show_grid and not is_polar:
        ax.grid(True, alpha=0.3, linestyle='--')
    elif not spec.show_grid and not is_polar:
        ax.grid(False)

    # Spine styling
    if not is_polar:
        for spine in ax.spines.values():
            spine.set_alpha(0.5)
            spine.set_linewidth(0.8)


def _add_legend(ax, spec: ChartSpec):
    """Add legend with styling."""
    if spec.show_legend and ax.get_legend_handles_labels()[1]:
        leg = ax.legend(
            loc=spec.legend_position,
            frameon=True,
            framealpha=0.9,
            edgecolor='#e5e7eb',
            fancybox=True,
            shadow=False,
        )
        leg.get_frame().set_linewidth(0.5)


def _add_data_labels(ax, xs, ys, labels_map):
    """Add data point annotations."""
    if not labels_map:
        return
    for idx, text in labels_map.items():
        i = int(idx)
        if 0 <= i < len(xs) and 0 <= i < len(ys):
            ax.annotate(
                str(text),
                (xs[i], ys[i]),
                textcoords="offset points",
                xytext=(0, 8),
                ha='center',
                fontsize=9,
                alpha=0.8,
            )


# ─── Chart renderers ─────────────────────────────────────────────────

def _render_line(ax, spec, colors):
    for i, ys in enumerate(spec.data):
        xs = spec.x_data if spec.x_data is not None else list(range(len(ys)))
        label = spec.series_labels[i] if i < len(spec.series_labels) else f"Series {i+1}"
        ax.plot(xs, ys, label=label, marker="o", linewidth=spec.line_width,
                color=colors[i], markersize=spec.marker_size)
        if spec.annotations:
            _add_data_labels(ax, xs, ys, spec.annotations)
    _add_legend(ax, spec)


def _render_bar(ax, spec, colors):
    import numpy as np
    cats = spec.x_data or [f"C{i}" for i in range(len(spec.data[0]))]
    n_series = len(spec.data)
    if n_series == 1:
        bars = ax.bar(cats, spec.data[0], color=colors[0], width=spec.bar_width,
                       edgecolor='white', linewidth=0.5)
        if spec.show_data_labels:
            ax.bar_label(bars, fmt='%.1f', fontsize=9)
    else:
        x = np.arange(len(cats))
        width = spec.bar_width / n_series
        for i, ys in enumerate(spec.data):
            offset = (i - n_series / 2) * width + width / 2
            label = spec.series_labels[i] if i < len(spec.series_labels) else f"Series {i+1}"
            bars = ax.bar(x + offset, ys, width, label=label, color=colors[i],
                          edgecolor='white', linewidth=0.5)
            if spec.show_data_labels:
                ax.bar_label(bars, fmt='%.1f', fontsize=8)
        ax.set_xticks(x)
        ax.set_xticklabels(cats)
        _add_legend(ax, spec)


def _render_scatter(ax, spec, colors):
    if not spec.x_data or not spec.data:
        raise ValueError("scatter requires x_data and data")
    for i, ys in enumerate(spec.data):
        label = spec.series_labels[i] if i < len(spec.series_labels) else f"Series {i+1}"
        ax.scatter(spec.x_data, ys, label=label, alpha=0.75, color=colors[i],
                   s=spec.marker_size * 15, edgecolors='white', linewidths=0.5)
    _add_legend(ax, spec)


def _render_pie(ax, spec, colors):
    if not spec.data or not spec.data[0]:
        raise ValueError("pie requires data[0] = list of values")
    labels = spec.series_labels or [f"S{i}" for i in range(len(spec.data[0]))]
    n = len(spec.data[0])
    pie_colors = _get_colors(spec, n)
    wedges, texts, autotexts = ax.pie(
        spec.data[0], labels=labels, autopct="%1.1f%%", startangle=90,
        colors=pie_colors, pctdistance=0.85,
        wedgeprops=dict(width=0.7, edgecolor='white', linewidth=2),
    )
    for t in autotexts:
        t.set_fontsize(spec.font_size - 2)
        t.set_fontweight('bold')


def _render_donut(ax, spec, colors):
    if not spec.data or not spec.data[0]:
        raise ValueError("donut requires data[0] = list of values")
    labels = spec.series_labels or [f"S{i}" for i in range(len(spec.data[0]))]
    n = len(spec.data[0])
    pie_colors = _get_colors(spec, n)
    wedges, texts, autotexts = ax.pie(
        spec.data[0], labels=labels, autopct="%1.1f%%", startangle=90,
        colors=pie_colors, pctdistance=0.78,
        wedgeprops=dict(width=0.4, edgecolor='white', linewidth=2.5),
    )
    for t in autotexts:
        t.set_fontsize(spec.font_size - 2)
        t.set_fontweight('bold')
    # Center circle
    centre_circle = ax.add_artist(
        __import__('matplotlib').patches.Circle((0, 0), 0.55, fc='white')
    )


def _render_hist(ax, spec, colors):
    for i, ys in enumerate(spec.data):
        label = spec.series_labels[i] if i < len(spec.series_labels) else f"Series {i+1}"
        ax.hist(ys, bins=20, alpha=0.7, label=label, color=colors[i],
                edgecolor='white', linewidth=0.5)
    _add_legend(ax, spec)


def _render_box(ax, spec, colors):
    bp = ax.boxplot(spec.data, labels=spec.series_labels or None, patch_artist=True,
                    medianprops=dict(color='#1e293b', linewidth=2))
    for i, patch in enumerate(bp['boxes']):
        patch.set_facecolor(colors[i % len(colors)])
        patch.set_alpha(0.7)


def _render_violin(ax, spec, colors):
    import numpy as np
    data_arrays = [np.array(d, dtype=float) for d in spec.data]
    parts = ax.violinplot(data_arrays, showmeans=True, showmedians=True)
    for i, pc in enumerate(parts['bodies']):
        pc.set_facecolor(colors[i % len(colors)])
        pc.set_alpha(0.7)
        pc.set_edgecolor('white')
        pc.set_linewidth(1)
    if spec.series_labels:
        ax.set_xticks(range(1, len(spec.data) + 1))
        ax.set_xticklabels(spec.series_labels)


def _render_heatmap(ax, spec, colors):
    import numpy as np
    arr = np.array(spec.data, dtype=float)
    im = ax.imshow(arr, cmap='viridis', aspect='auto')
    cbar = ax.figure.colorbar(im, ax=ax, shrink=0.8)
    cbar.ax.tick_params(labelsize=spec.font_size - 2)
    # Add value annotations
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            ax.text(j, i, f'{arr[i, j]:.1f}', ha='center', va='center',
                    fontsize=spec.font_size - 2, color='white' if arr[i, j] > arr.mean() else 'black')


def _render_area(ax, spec, colors):
    for i, ys in enumerate(spec.data):
        xs = spec.x_data if spec.x_data is not None else list(range(len(ys)))
        label = spec.series_labels[i] if i < len(spec.series_labels) else f"Series {i+1}"
        ax.fill_between(xs, ys, alpha=0.3, color=colors[i], label=label)
        ax.plot(xs, ys, color=colors[i], linewidth=spec.line_width)
    _add_legend(ax, spec)


def _render_stacked_bar(ax, spec, colors):
    import numpy as np
    cats = spec.x_data or [f"C{i}" for i in range(len(spec.data[0]))]
    x = np.arange(len(cats))
    bottom = np.zeros(len(spec.data[0]))
    for i, ys in enumerate(spec.data):
        label = spec.series_labels[i] if i < len(spec.series_labels) else f"Series {i+1}"
        bars = ax.bar(x, ys, spec.bar_width, bottom=bottom, label=label,
                      color=colors[i], edgecolor='white', linewidth=0.5)
        if spec.show_data_labels:
            ax.bar_label(bars, fmt='%.1f', fontsize=8)
        bottom += np.array(ys, dtype=float)
    ax.set_xticks(x)
    ax.set_xticklabels(cats)
    _add_legend(ax, spec)


def _render_stacked_area(ax, spec, colors):
    xs = spec.x_data if spec.x_data is not None else list(range(len(spec.data[0])))
    ax.stackplot(xs, *spec.data, labels=spec.series_labels or [f"S{i}" for i in range(len(spec.data))],
                 colors=colors, alpha=0.7)
    _add_legend(ax, spec)


def _render_hbar(ax, spec, colors):
    import numpy as np
    cats = spec.x_data or [f"C{i}" for i in range(len(spec.data[0]))]
    n_series = len(spec.data)
    if n_series == 1:
        ax.barh(cats, spec.data[0], color=colors[0], height=spec.bar_width,
                edgecolor='white', linewidth=0.5)
    else:
        y = np.arange(len(cats))
        height = spec.bar_width / n_series
        for i, ys in enumerate(spec.data):
            offset = (i - n_series / 2) * height + height / 2
            label = spec.series_labels[i] if i < len(spec.series_labels) else f"Series {i+1}"
            ax.barh(y + offset, ys, height, label=label, color=colors[i],
                    edgecolor='white', linewidth=0.5)
        ax.set_yticks(y)
        ax.set_yticklabels(cats)
        _add_legend(ax, spec)


def _render_radar(ax, spec, colors):
    import numpy as np
    categories = spec.x_data or [f"C{i}" for i in range(len(spec.data[0]))]
    n_cats = len(categories)
    angles = np.linspace(0, 2 * np.pi, n_cats, endpoint=False).tolist()
    angles += angles[:1]  # close the polygon

    for i, ys in enumerate(spec.data):
        values = list(ys) + list(ys[:1])
        label = spec.series_labels[i] if i < len(spec.series_labels) else f"Series {i+1}"
        ax.plot(angles, values, 'o-', linewidth=spec.line_width, label=label, color=colors[i])
        ax.fill(angles, values, alpha=0.15, color=colors[i])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=spec.font_size - 1)


def _render_waterfall(ax, spec, colors):
    import numpy as np
    if not spec.data or not spec.data[0]:
        raise ValueError("waterfall requires data[0]")
    values = [float(v) for v in spec.data[0]]
    cats = spec.x_data or [f"Step {i+1}" for i in range(len(values))]

    cumulative = [0]
    for v in values:
        cumulative.append(cumulative[-1] + v)

    bottoms = cumulative[:-1]
    bar_colors = []
    for v in values:
        bar_colors.append('#22c55e' if v >= 0 else '#ef4444')

    bars = ax.bar(cats, values, bottom=bottoms, color=bar_colors,
                  edgecolor='white', linewidth=0.5, width=spec.bar_width)

    # Connector lines
    for i in range(len(values) - 1):
        ax.plot([i, i + 1], [cumulative[i + 1], cumulative[i + 1]],
                color='#94a3b8', linewidth=0.8, linestyle='--')

    if spec.show_data_labels:
        for i, (b, v) in enumerate(zip(bottoms, values)):
            ax.text(i, b + v + 0.5, f'{v:+.1f}', ha='center', fontsize=9)


def _render_bubble(ax, spec, colors):
    """Bubble chart: data[0]=x, data[1]=y, data[2]=size."""
    if len(spec.data) < 2:
        raise ValueError("bubble requires at least 2 data series (x, y)")
    xs = spec.data[0] if not spec.x_data else spec.x_data
    ys = spec.data[1] if not spec.x_data else spec.data[0]
    sizes = spec.data[2] if len(spec.data) > 2 else [100] * len(xs)
    max_size = max(sizes) if sizes else 1
    norm_sizes = [s / max_size * 500 for s in sizes]

    n_series = 1
    label = spec.series_labels[0] if spec.series_labels else "Data"
    ax.scatter(xs, ys, s=norm_sizes, alpha=0.6, color=colors[0],
               label=label, edgecolors='white', linewidths=0.5)
    _add_legend(ax, spec)


def _render_combo(ax, spec, colors):
    """Combo chart: first series as bar, rest as lines."""
    import numpy as np
    cats = spec.x_data or [f"C{i}" for i in range(len(spec.data[0]))]

    if len(spec.data) < 2:
        # Fallback to bar
        label = spec.series_labels[0] if spec.series_labels else "Series 1"
        ax.bar(cats, spec.data[0], color=colors[0], width=spec.bar_width,
               edgecolor='white', linewidth=0.5, label=label)
    else:
        # First series: bar
        label_bar = spec.series_labels[0] if spec.series_labels else "Bar"
        ax.bar(cats, spec.data[0], color=colors[0], width=spec.bar_width,
               edgecolor='white', linewidth=0.5, label=label_bar, alpha=0.8)

        # Remaining series: line on secondary axis
        ax2 = ax.twinx()
        for i in range(1, len(spec.data)):
            label_line = spec.series_labels[i] if i < len(spec.series_labels) else f"Line {i}"
            ax2.plot(cats, spec.data[i], label=label_line, marker="s",
                     linewidth=spec.line_width, color=colors[i], markersize=spec.marker_size)

        # Merge legends
        handles1, labels1 = ax.get_legend_handles_labels()
        handles2, labels2 = ax2.get_legend_handles_labels()
        if spec.show_legend and (labels1 or labels2):
            ax.legend(handles1 + handles2, labels1 + labels2, loc=spec.legend_position,
                      frameon=True, framealpha=0.9)


# ─── Dispatcher ──────────────────────────────────────────────────────
RENDERERS = {
    "line":         _render_line,
    "bar":          _render_bar,
    "scatter":      _render_scatter,
    "pie":          _render_pie,
    "donut":        _render_donut,
    "hist":         _render_hist,
    "box":          _render_box,
    "violin":       _render_violin,
    "heatmap":      _render_heatmap,
    "area":         _render_area,
    "stacked_bar":  _render_stacked_bar,
    "stacked_area": _render_stacked_area,
    "hbar":         _render_hbar,
    "radar":        _render_radar,
    "waterfall":    _render_waterfall,
    "bubble":       _render_bubble,
    "combo":        _render_combo,
}


def generate_chart(paper_id: str, spec: ChartSpec, user_id=None, judul_paper=None, target_path: str = None) -> str:
    """Generate a chart PNG and return absolute path (thread-safe).

    Args:
        paper_id: Paper ID for organizing output directory.
        spec: ChartSpec with chart configuration.
        user_id: User ID for storage (optional).
        judul_paper: Paper title for storage (optional).
        target_path: Target filename from paper JSON Path (e.g.,
            'gambar/fig4_1_settling_time.png'). When provided, this overrides
            the random UUID filename. Basename is extracted and used.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.figure
    import matplotlib.style

    if not spec.kind:
        raise ValueError("spec.kind is required")
    if spec.kind not in RENDERERS:
        raise ValueError(f"unknown chart kind: {spec.kind}")
    if spec.data is None or len(spec.data) == 0:
        raise ValueError("spec.data is required and must be non-empty")

    safe_paper_id = str(paper_id) if paper_id else "default"
    out_dir = os.path.join(CHARTS_DIR, safe_paper_id)
    os.makedirs(out_dir, exist_ok=True)

    # Determine filename: use target_path if provided, else UUID
    if target_path:
        import re as _re
        base = _re.sub(r'[<>:"/\\\\|?*]', '_', os.path.basename(target_path))
        if not base:
            base = f"{str(uuid.uuid4())[:8]}.png"
        # Ensure .png extension
        root, fext = os.path.splitext(base)
        if fext.lower() not in ('.png', '.jpg', '.jpeg', '.svg', '.pdf'):
            base = root + '.png'
        # Avoid collisions
        final_name = base
        counter = 1
        while os.path.exists(os.path.join(out_dir, final_name)):
            final_name = f"{root}_{counter}.png"
            counter += 1
        chart_id = final_name
    else:
        chart_id = f"{str(uuid.uuid4())[:8]}.png"
    out_path = os.path.join(out_dir, chart_id)

    # Apply style to figure directly (thread-safe, no global state mutation)
    _theme_name = MPL_THEMES.get(spec.theme, "default")
    style_dict = matplotlib.style.library.get(_theme_name, {})
    with matplotlib.rc_context(style_dict):
        n_series = len(spec.data)
        colors = _get_colors(spec, max(n_series, len(spec.data[0]) if spec.data[0] else 1))

        is_polar = spec.kind == "radar"
        subplot_kw = {"projection": "polar"} if is_polar else {}
        fig = matplotlib.figure.Figure(figsize=spec.figsize, dpi=spec.dpi)
        ax = fig.add_subplot(111, **subplot_kw)

        try:
            _setup_axes(fig, ax, spec, is_polar=is_polar)
            renderer = RENDERERS[spec.kind]
            renderer(ax, spec, colors)

            fig.tight_layout()
            fig.savefig(out_path, bbox_inches="tight", dpi=spec.dpi, facecolor='white')
        finally:
            fig.clear()
            del fig

    # Save to user storage
    try:
        from utils.core.user_storage import get_username, save_image
        username = get_username(user_id=user_id) if user_id else "anonymous"
        save_image(username, judul_paper or "untitled", out_path)
    except Exception:
        pass

    log.info("chart generated: paper=%s kind=%s path=%s", safe_paper_id, spec.kind, out_path)
    return out_path


def render_chart_base64(spec: ChartSpec) -> str:
    """Render chart to base64 PNG string (for preview without saving to DB). Thread-safe."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.figure
    import matplotlib.style
    import io
    import base64

    if not spec.kind:
        raise ValueError("spec.kind is required")
    if spec.kind not in RENDERERS:
        raise ValueError(f"unknown chart kind: {spec.kind}")
    if spec.data is None or len(spec.data) == 0:
        raise ValueError("spec.data is required and must be non-empty")

    _apply_theme(spec)

    # Apply style to figure directly (thread-safe, no global state mutation)
    _theme_name = MPL_THEMES.get(spec.theme, "default")
    style_dict = matplotlib.style.library.get(_theme_name, {})
    with matplotlib.rc_context(style_dict):
        n_series = len(spec.data)
        colors = _get_colors(spec, max(n_series, len(spec.data[0]) if spec.data[0] else 1))

        is_polar = spec.kind == "radar"
        subplot_kw = {"projection": "polar"} if is_polar else {}
        fig = matplotlib.figure.Figure(figsize=spec.figsize, dpi=min(spec.dpi, 100))
        ax = fig.add_subplot(111, **subplot_kw)

        try:
            _setup_axes(fig, ax, spec, is_polar=is_polar)
            renderer = RENDERERS[spec.kind]
            renderer(ax, spec, colors)

            fig.tight_layout()

            buf = io.BytesIO()
            fig.savefig(buf, format='png', bbox_inches="tight",
                        dpi=min(spec.dpi, 100), facecolor='white')
            buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode('utf-8')
        finally:
            fig.clear()
            del fig

    return f"data:image/png;base64,{b64}"


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
            "preview": "\n".join(
                ["\t".join("" if c is None else str(c) for c in r) for r in rows[:10]]
            ),
        }
    elif ext in [".docx", ".doc"]:
        return _parse_docx_tables(file_path)
    elif ext == ".pdf":
        return _parse_pdf_tables(file_path)
    else:
        raise ValueError(f"unsupported file ext: {ext}")


def _rows_to_result(rows: list) -> dict:
    """Normalise a list-of-rows (first row = header) into the parse result dict."""
    rows = [r for r in rows if r is not None]
    if not rows:
        return {"columns": [], "rows": [], "n_rows": 0, "preview": "(empty)"}
    cols = ["" if c is None else str(c) for c in rows[0]]
    data = [["" if c is None else str(c) for c in r] for r in rows[1:]]
    return {
        "columns": cols,
        "rows": data[:50],
        "n_rows": len(data),
        "preview": "\n".join(
            ["".join("" if c is None else str(c) for c in r) for r in rows[:10]]
        ),
    }


def _parse_docx_tables(file_path: str) -> dict:
    """Extract the first table found in a Word document."""
    try:
        from docx import Document
    except ImportError:
        raise RuntimeError("python-docx not installed; cannot parse Word documents")

    document = Document(file_path)
    if not document.tables:
        raise ValueError("no tables found in Word document")

    table = document.tables[0]
    rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
    return _rows_to_result(rows)


def _parse_pdf_tables(file_path: str) -> dict:
    """Extract the first table found in a PDF using PyMuPDF's table finder."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("PyMuPDF not installed; cannot parse PDF documents")

    doc = fitz.open(file_path)
    try:
        for page in doc:
            finder = getattr(page, "find_tables", None)
            if finder is None:
                raise RuntimeError("PyMuPDF version too old for table extraction")
            tables = finder()
            for table in tables.tables:
                rows = table.extract()
                if rows and any(any(c not in (None, "") for c in r) for r in rows):
                    return _rows_to_result(rows)
    finally:
        doc.close()

    raise ValueError("no tables found in PDF document")
