"""Tests for chart_generator module (section 4 results graphs)."""
import os
import sys
import csv
import tempfile

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from chart_generator import generate_chart, parse_data_file, ChartSpec, CHARTS_DIR  # noqa: E402


PAPER_ID = "test"


def _assert_png(path: str):
    assert os.path.exists(path), f"missing: {path}"
    assert os.path.getsize(path) > 200, f"too small: {path}"
    with open(path, "rb") as f:
        head = f.read(8)
    assert head[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG file"


def test_line_chart():
    spec = ChartSpec(
        kind="line",
        title="Line Test",
        xlabel="t",
        ylabel="v",
        data=[[1, 2, 3, 4, 5], [2, 3, 4, 5, 6]],
        series_labels=["A", "B"],
    )
    out = generate_chart(PAPER_ID, spec)
    _assert_png(out)


def test_bar_chart_single_series():
    spec = ChartSpec(
        kind="bar",
        title="Bar Single",
        xlabel="cat",
        ylabel="count",
        data=[[10, 20, 15]],
        x_data=["X", "Y", "Z"],
    )
    out = generate_chart(PAPER_ID, spec)
    _assert_png(out)


def test_bar_chart_multi_series():
    spec = ChartSpec(
        kind="bar",
        title="Bar Multi",
        data=[[10, 20, 15], [12, 18, 22]],
        x_data=["X", "Y", "Z"],
        series_labels=["A", "B"],
    )
    out = generate_chart(PAPER_ID, spec)
    _assert_png(out)


def test_scatter_chart():
    spec = ChartSpec(
        kind="scatter",
        title="Scatter",
        xlabel="x",
        ylabel="y",
        data=[[1, 2, 3, 4]],
        x_data=[10, 20, 30, 40],
        series_labels=["pts"],
    )
    out = generate_chart(PAPER_ID, spec)
    _assert_png(out)


def test_hist_chart():
    spec = ChartSpec(
        kind="hist",
        title="Hist",
        data=[[1, 2, 2, 3, 3, 3, 4, 4, 4, 4, 5, 5, 6]],
        series_labels=["dist"],
    )
    out = generate_chart(PAPER_ID, spec)
    _assert_png(out)


def test_box_chart():
    spec = ChartSpec(
        kind="box",
        title="Box",
        data=[[1, 2, 3, 4, 5], [2, 3, 4, 5, 6, 7]],
        series_labels=["G1", "G2"],
    )
    out = generate_chart(PAPER_ID, spec)
    _assert_png(out)


def test_heatmap_chart():
    spec = ChartSpec(
        kind="heatmap",
        title="Heatmap",
        data=[[1, 2, 3], [4, 5, 6], [7, 8, 9]],
    )
    out = generate_chart(PAPER_ID, spec)
    _assert_png(out)


def test_pie_chart():
    spec = ChartSpec(
        kind="pie",
        title="Pie",
        data=[[30, 20, 50]],
        series_labels=["A", "B", "C"],
    )
    out = generate_chart(PAPER_ID, spec)
    _assert_png(out)


def test_invalid_kind_raises():
    spec = ChartSpec(kind="badkind", title="bad", data=[[1, 2, 3]])  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        generate_chart(PAPER_ID, spec)


def test_empty_data_raises():
    spec = ChartSpec(kind="line", title="empty", data=[])
    with pytest.raises(ValueError):
        generate_chart(PAPER_ID, spec)


def test_scatter_missing_x_raises():
    spec = ChartSpec(kind="scatter", title="bad", data=[[1, 2, 3]])
    with pytest.raises(ValueError):
        generate_chart(PAPER_ID, spec)


def test_pie_empty_values_raises():
    spec = ChartSpec(kind="pie", title="bad", data=[[]])
    with pytest.raises(ValueError):
        generate_chart(PAPER_ID, spec)


def test_parse_csv():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "value"])
        w.writerow(["1", "10"])
        w.writerow(["2", "20"])
        w.writerow(["3", "30"])
        path = f.name
    try:
        result = parse_data_file(path)
        assert result["columns"] == ["time", "value"]
        assert result["n_rows"] == 3
        assert len(result["rows"]) == 3
        assert "time" in result["preview"]
    finally:
        os.unlink(path)


def test_parse_tsv():
    with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, newline="") as f:
        f.write("a\tb\n1\t2\n3\t4\n")
        path = f.name
    try:
        result = parse_data_file(path)
        assert result["columns"] == ["a", "b"]
        assert result["n_rows"] == 2
    finally:
        os.unlink(path)


def test_parse_xlsx():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["col1", "col2"])
    ws.append([1, 2])
    ws.append([3, 4])
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        path = f.name
    try:
        wb.save(path)
        result = parse_data_file(path)
        assert result["columns"] == ["col1", "col2"]
        assert result["n_rows"] == 2
    finally:
        os.unlink(path)


def test_parse_unsupported_ext_raises():
    with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
        path = f.name
    try:
        with pytest.raises(ValueError):
            parse_data_file(path)
    finally:
        os.unlink(path)


def test_parse_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        parse_data_file("/nonexistent/path/file.csv")


def test_charts_dir_exists():
    assert os.path.isdir(CHARTS_DIR)
