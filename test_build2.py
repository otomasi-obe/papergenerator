import re

def build(user_prompt):
    rows = []
    columns = None
    kv_pattern = re.compile(r'(\w[\w\s]*?)\s*=\s*([\d.]+)\s*\w*')
    all_metrics = set()

    segments = re.split(r'(Config\d+|Konfigurasi\s*\d+)', user_prompt, flags=re.IGNORECASE)
    for i in range(1, len(segments), 2):
        config_name = segments[i].strip()
        rest = segments[i+1].strip() if i+1 < len(segments) else ""
        det_m = re.match(r'\s*\(([^)]+)\)\s*:\s*(.*)', rest)
        if not det_m:
            continue
        details = det_m.group(1).strip()
        metrics_str = det_m.group(2).strip()
        metrics_str = re.sub(r'[,.;]+$', '', metrics_str)

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
        return [], []

    normalized = []
    for row in rows:
        normalized.append([str(row.get(c, "")) for c in columns])
    return normalized, columns

prompt = (
    'create an image chart ... '
    'Config1 (7.4V 1000mAh 40cm/s): Daya=2.37W, Durasi=42min. '
    'Config2 (7.4V 1500mAh 60cm/s): Daya=3.55W, Durasi=38min; '
    'Config3 (7.4V 2000mAh 80cm/s): Daya=4.74W, Durasi=34min; '
    'Config4 (11.1V 1000mAh 40cm/s): Daya=3.22W, Durasi=28min; '
    'Config5 (11.1V 1500mAh 60cm/s): Daya=4.77W, Durasi=26min; '
    'Config6 (11.1V 2000mAh 80cm/s): Daya=6.44W, Durasi=24min; '
    'Config7 (11.1V 2200mAh 100cm/s): Daya=7.99W, Durasi=20min; '
    'Config8 (12.6V 2200mAh 100cm/s): Daya=8.69W, Durasi=19min. the end.'
)

tables, cols = build(prompt)
if tables:
    print(f"Rows: {len(tables)}")
    print(f"Cols: {cols}")
    for r in tables:
        print(f"  {r}")
else:
    print("ERROR")