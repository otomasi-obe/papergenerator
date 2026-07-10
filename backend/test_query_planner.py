"""Test query_planner.py"""
import sys
import json
sys.path.insert(0, '.')
from tools.Literatur.query_planner import _run_query_planner, run_query_planner_tool

test_topics = [
    "Pemanfaatan teknik kultur jaringan untuk konservasi tumbuhan langka",
    "Deep learning for medical image analysis",
    "Implementasi algoritma neural network untuk klasifikasi citra medis",
    "Studi kajian literatur tentang pengaruh perubahan iklim terhadap pertanian",
]

for topic in test_topics:
    print(f"\n{'='*60}")
    print(f"TOPIC: {topic}")
    print(f"{'='*60}")
    plan = _run_query_planner(topic)
    print(json.dumps(plan, indent=2, ensure_ascii=False))

# Test tool runner
print("\n\n=== TOOL RUNNER TEST ===")
result = run_query_planner_tool({"text": test_topics[0]})
print(json.dumps(result, indent=2, ensure_ascii=False))
