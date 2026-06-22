import dotenv, os, re, json

dotenv.load_dotenv('/home/sirobo/papergenerator/.env', override=False)
os.chdir('/home/sirobo/papergenerator/backend')

# Import the function directly
exec(open('tools/data/data_worker.py').read().split('def _generate_chart_from_rec')[0])

def _build_synthetic_tables_from_charts(recs, user_prompt):
    rows = []
    columns = None
    config_pattern = re.compile(
        r'(Config\d+|Konfigurasi\s*\d+)\s*\(([^)]+)\)\s*:\s*([^C]+?)(?=(?:Config\d+|Konfigurasi\s*\d+)|$)',
        re.IGNORECASE | re.DOTALL,
    )
    kv_pattern = re.compile(r'(\w[\w\s]*?)\s*=\s*([\d.]+)\s*\w*')
    all_metrics = set()

    for match in config_pattern.finditer(user_prompt):
        config_name = match.group(1).strip()
        details = match.group(2).strip()
        metrics_str = match.group(3).strip()
        metrics_str = re.sub(r'[.;,\s]+$', '', metrics_str)

        metrics = {}
        for km in kv_pattern.finditer(metrics_str):
            key = km.group(1).strip()
            val = km.group(2)
            metrics[key] = val
            all_metrics.add(key)

        row = {"Konfigurasi": config_name, "Detail": details, **metrics}
        rows.append(row)

    if rows and all_metrics:
        columns = ["Konfigurasi", "Detail"] + sorted(all_metrics)

    if not rows or not columns:
        return []

    normalized = []
    for row in rows:
        normalized.append([str(row.get(c, "")) for c in columns])

    def _detect_column_types(columns, rows):
        types = []
        for ci in range(len(columns)):
            sample = [r[ci] for r in rows[:20] if ci < len(r) and r[ci] not in ("", None)]
            if not sample:
                types.append("kategori")
                continue
            try:
                [float(v.replace(",", "")) for v in sample]
                types.append("numerik")
            except (ValueError, TypeError):
                types.append("kategori")
        return types

    table = {
        "name": "Data (diextrak dari instruksi)",
        "description": "Data yang diekstrak otomatis dari instruksi teks.",
        "columns": columns,
        "column_types": _detect_column_types(columns, normalized),
        "rows": normalized,
        "analysis": "Data diekstrak dari instruksi user.",
    }
    return [table]

user_prompt = 'create an image "A combined bar and line chart with dual y-axes. The x-axis represents \'Konfigurasi\' from 1 to 8, corresponding to the 8 rows in the battery test data. The left y-axis (blue) represents \'Daya (W)\' ranging from 0 to 10 W, shown as blue bars. The right y-axis (red) represents \'Durasi Operasi (menit)\' ranging from 0 to 50 minutes, shown as a red line with circle markers. The 8 configurations are: Config1 (7.4V 1000mAh 40cm/s): Daya=2.37W, Durasi=42min. Config2 (7.4V 1500mAh 60cm/s): Daya=3.55W, Durasi=38min; Config3 (7.4V 2000mAh 80cm/s): Daya=4.74W, Durasi=34min; Config4 (11.1V 1000mAh 40cm/s): Daya=3.22W, Durasi=28min; Config5 (11.1V 1500mAh 60cm/s): Daya=4.77W, Durasi=26min; Config6 (11.1V 2000mAh 80cm/s): Daya=6.44W, Durasi=24min; Config7 (11.1V 2200mAh 100cm/s): Daya=7.99W, Durasi=20min; Config8 (12.6V 2200mAh 100cm/s): Daya=8.69W, Durasi=19min. The chart has a white background with light gray grid lines."'

fake_recs = [
    {
        "kind": "combo",
        "title": "Pengaruh Kecepatan terhadap Daya dan Durasi Operasi",
        "table_index": 0,
        "x_column": "Konfigurasi",
        "y_columns": ["Daya", "Durasi Operasi"],
    }
]

tables = _build_synthetic_tables_from_charts(fake_recs, user_prompt)

if tables:
    t = tables[0]
    print(f"Table: {t['name']}")
    print(f"Columns: {t['columns']}")
    print(f"Types: {t['column_types']}")
    print(f"Rows: {len(t['rows'])}")
    for i, row in enumerate(t['rows'][:3]):
        print(f"  Row {i+1}: {row}")
    print("...")
    print(f"Last row: {t['rows'][-1]}")
    print("\nSUCCESS")
else:
    print("ERROR: No tables built!")
