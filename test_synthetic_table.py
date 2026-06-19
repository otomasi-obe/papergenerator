import dotenv, os, sys

dotenv.load_dotenv('/home/sirobo/papergenerator/.env', override=False)
sys.path.insert(0, '/home/sirobo/papergenerator/backend')

# Import just the function we need
import re
from tools.data.data_worker import _build_synthetic_tables_from_charts

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
else:
    print("ERROR: No tables built!")
