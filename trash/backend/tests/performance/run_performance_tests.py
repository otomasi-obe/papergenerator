#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
from datetime import datetime


def run_scenario(name, users, duration, spawn_rate):
    print(f"\n{'='*70}")
    print(f"Running Scenario: {name}")
    print(f"Users: {users}, Duration: {duration}s, Spawn Rate: {spawn_rate}/s")
    print(f"{'='*70}\n")

    env = os.environ.copy()
    env['MOCK_AI_RESPONSES'] = '1'

    reports_dir = "backend/tests/performance/reports"
    os.makedirs(reports_dir, exist_ok=True)

    cmd = [
        "locust",
        "-f", "backend/tests/performance/locustfile.py",
        "--headless",
        "--users", str(users),
        "--spawn-rate", str(spawn_rate),
        "--run-time", f"{duration}s",
        "--host", "http://localhost:5000",
        "--html", f"{reports_dir}/{name}.html",
        "--csv", f"{reports_dir}/{name}"
    ]

    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    return {
        "success": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode
    }

def parse_locust_output(output):
    lines = output.split('\n')
    stats = {}

    for line in lines:
        if 'requests/s' in line.lower():
            parts = line.split()
            for i, part in enumerate(parts):
                if 'requests/s' in part.lower() and i > 0:
                    try:
                        stats['rps'] = float(parts[i-1])
                    except (ValueError, IndexError):
                        pass

        if 'response time' in line.lower() or 'avg' in line.lower():
            if 'ms' in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part.replace('.', '').isdigit():
                        try:
                            stats['avg_response_time'] = float(part)
                            break
                        except ValueError:
                            pass

    return stats

def main():
    print("="*70)
    print("PERFORMANCE TESTING - CYCLE 40")
    print("="*70)

    scenarios = [
        ("normal_load", 10, 60, 1),
        ("peak_load", 25, 60, 2),
        ("stress_test", 50, 60, 5),
    ]

    results = {}

    for name, users, duration, spawn_rate in scenarios:
        result = run_scenario(name, users, duration, spawn_rate)

        stats = parse_locust_output(result['stdout'])

        results[name] = {
            "users": users,
            "duration": duration,
            "spawn_rate": spawn_rate,
            "success": result['success'],
            "returncode": result['returncode'],
            "stats": stats,
            "output_preview": result['stdout'][-500:] if result['stdout'] else ""
        }

        print(f"\nScenario '{name}' completed:")
        print(f"  Success: {result['success']}")
        print(f"  Stats: {stats}")

        time.sleep(2)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_file = f"backend/tests/performance/reports/summary_{timestamp}.json"

    with open(summary_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*70}")
    print("Performance Testing Complete")
    print(f"Summary saved to: {summary_file}")
    print(f"{'='*70}\n")

    all_success = all(r['success'] for r in results.values())
    return 0 if all_success else 1

if __name__ == "__main__":
    sys.exit(main())
