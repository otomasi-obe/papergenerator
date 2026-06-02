#!/usr/bin/env python3
"""
Test Suite for Performance Testing Infrastructure
Verifies all components work correctly
"""

import os

import pytest
import requests
from performance_analyzer import PerformanceAnalyzer


class TestMockServer:
    """Test simplified mock server endpoints"""

    BASE_URL = "http://localhost:5000"

    def test_health_endpoint(self):
        """Test health endpoint returns correct response"""
        try:
            response = requests.get(f"{self.BASE_URL}/api/health", timeout=5)
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'ok'
            assert 'timestamp' in data
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Mock server not running: {e}")

    def test_login_success(self):
        """Test successful login"""
        try:
            response = requests.post(
                f"{self.BASE_URL}/api/auth/login",
                json={"username": "testuser", "password": "testpass123"},
                timeout=5
            )
            assert response.status_code == 200
            data = response.json()
            assert 'token' in data
            assert data['username'] == 'testuser'
        except requests.exceptions.RequestException:
            pytest.skip("Mock server not running")

    def test_login_failure(self):
        """Test failed login with wrong credentials"""
        try:
            response = requests.post(
                f"{self.BASE_URL}/api/auth/login",
                json={"username": "wrong", "password": "wrong"},
                timeout=5
            )
            assert response.status_code == 401
        except requests.exceptions.RequestException:
            pytest.skip("Mock server not running")

    def test_generate_requires_auth(self):
        """Test generate endpoint requires authentication"""
        try:
            response = requests.post(
                f"{self.BASE_URL}/api/generate",
                json={"prompt": "test", "section": "abstract"},
                timeout=5
            )
            assert response.status_code == 401
        except requests.exceptions.RequestException:
            pytest.skip("Mock server not running")

    def test_generate_with_auth(self):
        """Test generate endpoint with valid token"""
        try:
            # Login first
            login_resp = requests.post(
                f"{self.BASE_URL}/api/auth/login",
                json={"username": "testuser", "password": "testpass123"},
                timeout=5
            )
            token = login_resp.json()['token']

            # Generate
            response = requests.post(
                f"{self.BASE_URL}/api/generate",
                json={"prompt": "AI in healthcare", "section": "abstract"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=5
            )
            assert response.status_code == 200
            data = response.json()
            assert 'content' in data
            assert 'section' in data
        except requests.exceptions.RequestException:
            pytest.skip("Mock server not running")

class TestPerformanceAnalyzer:
    """Test performance analyzer module"""

    def test_analyzer_initialization(self):
        """Test analyzer can be initialized"""
        analyzer = PerformanceAnalyzer()
        assert analyzer.reports_dir is not None

    def test_parse_stats_csv_missing_file(self):
        """Test parsing non-existent stats file"""
        analyzer = PerformanceAnalyzer()
        result = analyzer.parse_stats_csv("nonexistent_scenario")
        assert 'error' in result

    def test_parse_failures_csv_missing_file(self):
        """Test parsing non-existent failures file"""
        analyzer = PerformanceAnalyzer()
        result = analyzer.parse_failures_csv("nonexistent_scenario")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_generate_report(self):
        """Test report generation"""
        analyzer = PerformanceAnalyzer()
        scenarios = [
            ("normal_load", 10, 60, 1),
            ("peak_load", 25, 60, 2),
        ]
        report = analyzer.generate_report(scenarios)

        assert 'timestamp' in report
        assert 'scenarios' in report
        assert 'overall_summary' in report
        assert len(report['scenarios']) == 2

class TestInfrastructure:
    """Test infrastructure files and directories"""

    def test_reports_directory_exists(self):
        """Test reports directory exists"""
        assert os.path.exists("backend/tests/performance/reports")

    def test_locustfile_exists(self):
        """Test locustfile exists"""
        assert os.path.exists("backend/tests/performance/locustfile.py")

    def test_run_script_exists(self):
        """Test run script exists"""
        assert os.path.exists("backend/tests/performance/run_performance_tests.py")

    def test_mock_server_exists(self):
        """Test mock server exists"""
        assert os.path.exists("backend/tests/performance/simple_mock_server.py")

    def test_analyzer_exists(self):
        """Test analyzer module exists"""
        assert os.path.exists("backend/tests/performance/performance_analyzer.py")

    def test_readme_exists(self):
        """Test README exists"""
        assert os.path.exists("backend/tests/performance/README.md")

    def test_troubleshooting_guide_exists(self):
        """Test troubleshooting guide exists"""
        assert os.path.exists("backend/tests/performance/TROUBLESHOOTING.md")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
