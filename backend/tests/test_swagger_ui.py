"""
Test Swagger UI Accessibility
==============================
Ensures Swagger UI and OpenAPI spec endpoints are accessible.
"""

from pathlib import Path

import pytest


class TestSwaggerUI:
    """Test suite for Swagger UI accessibility."""

    def test_swagger_ui_endpoint_exists(self, client):
        """Test that /api/docs endpoint exists and returns HTML."""
        response = client.get('/api/docs')
        assert response.status_code == 200, \
            f"Expected 200, got {response.status_code}"
        assert response.content_type.startswith('text/html'), \
            f"Expected text/html, got {response.content_type}"

    def test_swagger_ui_contains_swagger_bundle(self, client):
        """Test that Swagger UI HTML includes Swagger UI bundle."""
        response = client.get('/api/docs')
        html = response.data.decode('utf-8')

        assert 'swagger-ui' in html.lower(), \
            "Swagger UI HTML should contain 'swagger-ui'"
        assert 'SwaggerUIBundle' in html, \
            "Swagger UI HTML should contain SwaggerUIBundle"

    def test_swagger_ui_points_to_openapi_spec(self, client):
        """Test that Swagger UI is configured to load openapi.yaml."""
        response = client.get('/api/docs')
        html = response.data.decode('utf-8')

        assert '/api/openapi.yaml' in html, \
            "Swagger UI should point to /api/openapi.yaml"

    def test_openapi_yaml_endpoint_exists(self, client):
        """Test that /api/openapi.yaml endpoint exists."""
        response = client.get('/api/openapi.yaml')
        assert response.status_code == 200, \
            f"Expected 200, got {response.status_code}"

    def test_openapi_yaml_returns_yaml(self, client):
        """Test that /api/openapi.yaml returns YAML content."""
        response = client.get('/api/openapi.yaml')

        content_type = response.content_type
        assert 'yaml' in content_type or 'text/plain' in content_type, \
            f"Expected YAML content type, got {content_type}"

    def test_openapi_yaml_is_valid(self, client):
        """Test that /api/openapi.yaml returns valid YAML."""
        import yaml

        response = client.get('/api/openapi.yaml')
        data = response.data.decode('utf-8')

        try:
            spec = yaml.safe_load(data)
            assert spec is not None, "Parsed YAML is None"
            assert 'openapi' in spec, "Missing 'openapi' field in spec"
        except yaml.YAMLError as e:
            pytest.fail(f"Invalid YAML returned: {e}")

    def test_openapi_yaml_has_correct_structure(self, client):
        """Test that returned OpenAPI spec has correct structure."""
        import yaml

        response = client.get('/api/openapi.yaml')
        spec = yaml.safe_load(response.data.decode('utf-8'))

        required_fields = ['openapi', 'info', 'paths']
        for field in required_fields:
            assert field in spec, f"Missing required field: {field}"

    def test_swagger_ui_title(self, client):
        """Test that Swagger UI has a proper title."""
        response = client.get('/api/docs')
        html = response.data.decode('utf-8')

        assert '<title>' in html, "HTML should have a title tag"
        assert 'API' in html or 'Swagger' in html, \
            "Title should mention API or Swagger"

    def test_swagger_ui_uses_cdn(self, client):
        """Test that Swagger UI uses CDN resources."""
        response = client.get('/api/docs')
        html = response.data.decode('utf-8')

        assert 'cdn.jsdelivr.net' in html or 'unpkg.com' in html, \
            "Swagger UI should use CDN for resources"

    def test_openapi_spec_matches_file(self, client):
        """Test that served spec matches openapi.yaml file."""
        import yaml

        response = client.get('/api/openapi.yaml')
        served_spec = yaml.safe_load(response.data.decode('utf-8'))

        spec_path = Path(__file__).parent.parent / "openapi.yaml"
        with open(spec_path, 'r', encoding='utf-8') as f:
            file_spec = yaml.safe_load(f)

        assert served_spec['openapi'] == file_spec['openapi'], \
            "Served spec version doesn't match file"
        assert served_spec['info']['title'] == file_spec['info']['title'], \
            "Served spec title doesn't match file"
        assert len(served_spec['paths']) == len(file_spec['paths']), \
            "Served spec has different number of paths than file"
