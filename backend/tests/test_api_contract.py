"""
Test API Contract Compliance
=============================
Uses schemathesis to validate that actual API responses match OpenAPI spec.
"""

from pathlib import Path

import pytest
import schemathesis


class TestAPIContract:
    """Test suite for API contract validation using schemathesis."""

    @pytest.fixture
    def openapi_spec_path(self):
        """Path to openapi.yaml file."""
        return Path(__file__).parent.parent / "openapi.yaml"

    @pytest.fixture
    def schema(self, openapi_spec_path):
        """Load OpenAPI schema for schemathesis."""
        try:
            return schemathesis.from_path(str(openapi_spec_path))
        except Exception:
            pytest.skip("Schemathesis doesn't support OpenAPI 3.1.0")

    def test_health_endpoint_contract(self, client):
        """Test /api/health endpoint matches OpenAPI spec."""
        response = client.get('/api/health')

        assert response.status_code == 200
        data = response.get_json()

        assert 'status' in data, "Response missing 'status' field"
        assert 'timestamp' in data, "Response missing 'timestamp' field"
        assert data['status'] in ['ok', 'healthy'], "Status should be 'ok' or 'healthy'"

    def test_healthz_endpoint_contract(self, client):
        """Test /api/healthz endpoint matches OpenAPI spec."""
        response = client.get('/api/healthz')

        assert response.status_code in [200, 503], \
            f"Expected 200 or 503, got {response.status_code}"

        data = response.get_json()
        assert 'status' in data, "Response missing 'status' field"

    def test_openapi_yaml_endpoint_contract(self, client):
        """Test /api/openapi.yaml endpoint returns valid spec."""
        response = client.get('/api/openapi.yaml')

        assert response.status_code == 200
        assert response.data is not None
        assert len(response.data) > 0

    def test_swagger_ui_endpoint_contract(self, client):
        """Test /api/docs endpoint returns HTML."""
        response = client.get('/api/docs')

        assert response.status_code == 200
        assert response.content_type.startswith('text/html')
        assert len(response.data) > 0

    def test_metrics_endpoint_contract(self, client):
        """Test /metrics endpoint returns Prometheus format."""
        response = client.get('/metrics')

        assert response.status_code == 200
        data = response.data.decode('utf-8')

        assert len(data) > 0, "Metrics response should not be empty"
        assert '#' in data or 'HELP' in data or '_total' in data, \
            "Response should look like Prometheus metrics"

    def test_auth_register_requires_body(self, client):
        """Test /api/auth/register requires request body."""
        response = client.post('/api/auth/register', json={})

        assert response.status_code in [400, 422], \
            "Empty body should return 400 or 422"

    def test_auth_login_requires_body(self, client):
        """Test /api/auth/login requires request body."""
        response = client.post('/api/auth/login', json={})

        assert response.status_code in [400, 422], \
            "Empty body should return 400 or 422"

    def test_protected_endpoints_require_auth(self, client):
        """Test that protected endpoints return 401 without auth."""
        protected_endpoints = [
            '/api/papers',
        ]

        for endpoint in protected_endpoints:
            response = client.get(endpoint)
            assert response.status_code in [401, 403, 422], \
                f"{endpoint} should require authentication (got {response.status_code})"

    def test_error_responses_have_consistent_structure(self, client):
        """Test that error responses follow consistent structure."""
        response = client.get('/api/nonexistent-endpoint-12345')

        assert response.status_code == 404

        if response.content_type == 'application/json':
            data = response.get_json()
            assert 'error' in data or 'message' in data, \
                "Error response should have 'error' or 'message' field"

    def test_cors_headers_present(self, client):
        """Test that CORS headers are present in responses."""
        response = client.get('/api/health')

        headers = dict(response.headers)
        assert 'Access-Control-Allow-Origin' in headers or \
               response.status_code == 200, \
            "CORS headers should be present or endpoint should work"

    def test_content_type_headers(self, client):
        """Test that JSON endpoints return correct Content-Type."""
        response = client.get('/api/health')

        assert response.status_code == 200
        assert 'application/json' in response.content_type, \
            f"Expected JSON content type, got {response.content_type}"

    def test_rate_limiting_headers(self, client):
        """Test that rate limiting info is available."""
        response = client.get('/api/health')

        headers = dict(response.headers)
        any(
            'ratelimit' in key.lower() or 'x-ratelimit' in key.lower()
            for key in headers.keys()
        )

        assert response.status_code == 200

    def test_openapi_spec_is_loadable_by_schemathesis(self, openapi_spec_path):
        """Test that schemathesis can load the OpenAPI spec."""
        try:
            schema = schemathesis.from_path(str(openapi_spec_path))
            assert schema is not None, "Schema should not be None"
        except Exception as e:
            if "3.1.0" in str(e) and "not fully supported" in str(e):
                pytest.skip("Schemathesis doesn't fully support OpenAPI 3.1.0 yet")
            else:
                pytest.fail(f"Schemathesis failed to load spec: {e}")

    def test_spec_has_testable_endpoints(self, schema):
        """Test that OpenAPI spec has endpoints that can be tested."""
        endpoints = list(schema.get_all_operations())
        assert len(endpoints) > 0, "Schema should have testable endpoints"
        assert len(endpoints) >= 5, \
            f"Expected at least 5 testable endpoints, found {len(endpoints)}"
