#!/usr/bin/env python3
"""
Performance Analysis Module
Parses Locust CSV reports and generates comprehensive performance analysis
"""

import csv
import json
import os
from datetime import datetime
from typing import Any, Dict, List


class PerformanceAnalyzer:
    def __init__(self, reports_dir: str = "backend/tests/performance/reports"):
        self.reports_dir = reports_dir

    def parse_stats_csv(self, scenario_name: str) -> Dict[str, Any]:
        """Parse stats CSV file for a scenario"""
        csv_path = os.path.join(self.reports_dir, f"{scenario_name}_stats.csv")

        if not os.path.exists(csv_path):
            return {"error": f"Stats file not found: {csv_path}"}

        stats = []
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['Type'] != '':  # Skip aggregated row
                    stats.append({
                        'name': row['Name'],
                        'request_count': int(row['Request Count']) if row['Request Count'] else 0,
                        'failure_count': int(row['Failure Count']) if row['Failure Count'] else 0,
                        'median_response_time': float(row['Median Response Time']) if row['Median Response Time'] else 0,
                        'average_response_time': float(row['Average Response Time']) if row['Average Response Time'] else 0,
                        'min_response_time': int(row['Min Response Time']) if row['Min Response Time'] else 0,
                        'max_response_time': int(row['Max Response Time']) if row['Max Response Time'] else 0,
                        'requests_per_sec': float(row['Requests/s']) if row['Requests/s'] else 0,
                        'failures_per_sec': float(row['Failures/s']) if row['Failures/s'] else 0,
                        'p95': row['95%'],
                        'p99': row['99%']
                    })

        return {
            'scenario': scenario_name,
            'endpoints': stats,
            'total_requests': sum(s['request_count'] for s in stats),
            'total_failures': sum(s['failure_count'] for s in stats),
            'avg_rps': sum(s['requests_per_sec'] for s in stats)
        }

    def parse_failures_csv(self, scenario_name: str) -> List[Dict[str, Any]]:
        """Parse failures CSV file for a scenario"""
        csv_path = os.path.join(self.reports_dir, f"{scenario_name}_failures.csv")

        if not os.path.exists(csv_path):
            return []

        failures = []
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                failures.append({
                    'method': row.get('Method', ''),
                    'name': row.get('Name', ''),
                    'error': row.get('Error', ''),
                    'occurrences': int(row.get('Occurrences', 0)) if row.get('Occurrences') else 0
                })

        return failures

    def analyze_scenario(self, scenario_name: str, users: int, duration: int) -> Dict[str, Any]:
        """Comprehensive analysis for a scenario"""
        stats = self.parse_stats_csv(scenario_name)
        failures = self.parse_failures_csv(scenario_name)

        analysis = {
            'scenario': scenario_name,
            'configuration': {
                'users': users,
                'duration': duration
            },
            'stats': stats,
            'failures': failures,
            'summary': {
                'total_requests': stats.get('total_requests', 0),
                'total_failures': stats.get('total_failures', 0),
                'success_rate': 0,
                'avg_throughput': stats.get('avg_rps', 0)
            }
        }

        # Calculate success rate
        total_req = stats.get('total_requests', 0)
        total_fail = stats.get('total_failures', 0)
        if total_req > 0:
            analysis['summary']['success_rate'] = ((total_req - total_fail) / total_req) * 100

        return analysis

    def generate_report(self, scenarios: List[tuple]) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'scenarios': [],
            'overall_summary': {
                'total_requests': 0,
                'total_failures': 0,
                'avg_success_rate': 0
            }
        }

        for scenario_name, users, duration, spawn_rate in scenarios:
            analysis = self.analyze_scenario(scenario_name, users, duration)
            report['scenarios'].append(analysis)

            report['overall_summary']['total_requests'] += analysis['summary']['total_requests']
            report['overall_summary']['total_failures'] += analysis['summary']['total_failures']

        # Calculate overall success rate
        total_req = report['overall_summary']['total_requests']
        total_fail = report['overall_summary']['total_failures']
        if total_req > 0:
            report['overall_summary']['avg_success_rate'] = ((total_req - total_fail) / total_req) * 100

        return report

    def save_report(self, report: Dict[str, Any], filename: str = None):
        """Save report to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"performance_analysis_{timestamp}.json"

        filepath = os.path.join(self.reports_dir, filename)
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)

        return filepath

if __name__ == "__main__":
    analyzer = PerformanceAnalyzer()

    scenarios = [
        ("normal_load", 10, 60, 1),
        ("peak_load", 25, 60, 2),
        ("stress_test", 50, 60, 5),
    ]

    report = analyzer.generate_report(scenarios)
    filepath = analyzer.save_report(report)

    print(f"Performance analysis report saved to: {filepath}")
    print("\nOverall Summary:")
    print(f"  Total Requests: {report['overall_summary']['total_requests']}")
    print(f"  Total Failures: {report['overall_summary']['total_failures']}")
    print(f"  Success Rate: {report['overall_summary']['avg_success_rate']:.2f}%")
