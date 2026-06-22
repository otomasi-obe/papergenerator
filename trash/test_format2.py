import dotenv, os, json, sys

dotenv.load_dotenv('/home/sirobo/papergenerator/.env', override=False)
sys.path.insert(0, '/home/sirobo/papergenerator/backend')

# Direct import (skip __init__.py chain)
import importlib, importlib.util, importlib.machinery

def import_from_path(name, fpath):
    loader = importlib.machinery.SourceFileLoader(name, fpath)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module

# Load dependencies manually
import_from_path('tools.data.dataFormating', '/home/sirobo/papergenerator/backend/tools/data/dataFormating.py')

# Now get the function
from tools.data.dataFormating import format_data_with_ai

user_prompt = """create an image "A combined bar and line chart with dual y-axes. The x-axis represents 'Konfigurasi' from 1 to 8, corresponding to the 8 rows in the battery test data. The left y-axis (blue) represents 'Daya (W)' ranging from 0 to 10 W, shown as blue bars. The right y-axis (red) represents 'Durasi Operasi (menit)' ranging from 0 to 50 minutes, shown as a red line with circle markers. The 8 configurations are: Config1 (7.4V 1000mAh 40cm/s): Daya=2.37W, Durasi=42min. Config2 (7.4V 1500mAh 60cm/s): Daya=3.55W, Durasi=38min; Config3 (7.4V 2000mAh 80cm/s): Daya=4.74W, Durasi=34min; Config4 (11.1V 1000mAh 40cm/s): Daya=3.22W, Durasi=28min; Config5 (11.1V 1500mAh 60cm/s): Daya=4.77W, Durasi=26min; Config6 (11.1V 2000mAh 80cm/s): Daya=6.44W, Durasi=24min; Config7 (11.1V 2200mAh 100cm/s): Daya=7.99W, Durasi=20min; Config8 (12.6V 2200mAh 100cm/s): Daya=8.69W, Durasi=19min. The chart has a white background with light gray grid lines. Title 'Pengaruh Kecepatan terhadap Daya dan Durasi Operasi' centered. X-axis label 'Konfigurasi (Tegangan, Kapasitas, Kecepatan)'. Left y-axis 'Daya (W)' in blue, right y-axis 'Durasi Operasi (menit)' in red. A legend at the top-right, and Clean academic style. White background, and and Clean academic paper figure style."""

print("Calling format_data_with_ai...")
result = format_data_with_ai(user_prompt, filename="Text Input")
print("TABLES:", len(result.get("tables", [])))
print("CHARTS:", len(result.get("chart_recommendations", [])))
print("MODEL:", result.get("_model_used", "?"))
if not result.get("tables"):
    print("SUMMARY:", json.dumps(result.get("summary", {}), indent=2, ensure_ascii=False))
    raw = result.get("_raw_response", "")
    if raw:
        print("RAW_RESPONSE:", raw[:500])
else:
    for t in result.get("tables", []):
        print(f"  Table: {t.get('name')} cols={len(t.get('columns',[]))} rows={len(t.get('rows',[]))}")
    for c in result.get("chart_recommendations", []):
        print(f"  Chart: {c.get('title')} kind={c.get('kind')}")

print("DONE")