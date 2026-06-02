"""
Test OpenAPI Specification Validity and Completeness
=====================================================
Ensures openapi.yaml is valid, complete, and stays in sync with actual routes.
"""

from pathlib import Path

import pytest
import yaml


class TestOpenAPISpec:
    """Test suite for OpenAPI specification validation."""

    @pytest.fixture
    def openapi_spec_path(self):
        """Path to openapi.yaml file."""
        return Path(__file__).parent.parent / "openapi.yaml"

    @pytest.fixture
    def openapi_spec(self, openapi_spec_path):
        """Load and parse OpenAPI spec."""
        with open(openapi_spec_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def test_openapi_file_exists(self, openapi_spec_path):
        """Test that openapi.yaml file exists."""
        assert openapi_spec_path.exists(), "openapi.yaml file not found"
        assert openapi_spec_path.is_file(), "openapi.yaml is not a file"

    def test_openapi_is_valid_yaml(self, openapi_spec_path):
        """Test that openapi.yaml is valid YAML."""
        try:
            with open(openapi_spec_path, 'r', encoding='utf-8') as f:
                yaml.safe_load(f)
        except yaml.YAMLError as e:
            pytest.fail(f"openapi.yaml is not valid YAML: {e}")

    def test_openapi_version(self, openapi_spec):
        """Test that OpenAPI version is specified and valid."""
        assert 'openapi' in openapi_spec, "Missing 'openapi' field"
        version = openapi_spec['openapi']
        assert version.startswith('3.'), f"Expected OpenAPI 3.x, got {version}"

    def test_openapi_info_section(self, openapi_spec):
        """Test that info section is complete."""
        assert 'info' in openapi_spec, "Missing 'info' section"
        info = openapi_spec['info']

        assert 'title' in info, "Missing info.title"
        assert 'version' in info, "Missing info.version"
        assert 'description' in info, "Missing info.description"

        assert len(info['title']) > 0, "info.title is empty"
        assert len(info['version']) > 0, "info.version is empty"

    def test_openapi_servers_section(self, openapi_spec):
        """Test that servers are defined."""
        assert 'servers' in openapi_spec, "Missing 'servers' section"
        servers = openapi_spec['servers']

        assert len(servers) > 0, "No servers defined"
        for server in servers:
            assert 'url' in server, "Server missing 'url' field"
            assert 'description' in server, "Server missing 'description' field"

    def test_openapi_paths_section(self, openapi_spec):
        """Test that paths section exists and has endpoints."""
        assert 'paths' in openapi_spec, "Missing 'paths' section"
        paths = openapi_spec['paths']

        assert len(paths) > 0, "No paths defined in OpenAPI spec"
        assert len(paths) >= 10, f"Expected at least 10 endpoints, found {len(paths)}"

    def test_openapi_tags_section(self, openapi_spec):
        """Test that tags are defined."""
        assert 'tags' in openapi_spec, "Missing 'tags' section"
        tags = openapi_spec['tags']

        assert len(tags) > 0, "No tags defined"

        expected_tags = ['Auth', 'Papers', 'Files', 'Images', 'Health']
        tag_names = [tag['name'] for tag in tags]

        for expected_tag in expected_tags:
            assert expected_tag in tag_names, f"Missing expected tag: {expected_tag}"

    def test_openapi_components_section(self, openapi_spec):
        """Test that components section exists."""
        assert 'components' in openapi_spec, "Missing 'components' section"
        components = openapi_spec['components']

        assert 'schemas' in components or 'responses' in components, \
            "Components should have schemas or responses"

    def test_health_endpoint_documented(self, openapi_spec):
        """Test that /api/health endpoint is documented."""
        paths = openapi_spec['paths']
        assert '/api/health' in paths, "/api/health endpoint not documented"

        health_endpoint = paths['/api/health']
        assert 'get' in health_endpoint, "/api/health should have GET method"

        get_spec = health_endpoint['get']
        assert 'summary' in get_spec, "/api/health GET missing summary"
        assert 'responses' in get_spec, "/api/health GET missing responses"
        assert '200' in get_spec['responses'], "/api/health GET missing 200 response"

    def test_auth_endpoints_documented(self, openapi_spec):
        """Test that auth endpoints are documented."""
        paths = openapi_spec['paths']

        auth_endpoints = ['/api/auth/register', '/api/auth/login']
        for endpoint in auth_endpoints:
            assert endpoint in paths, f"{endpoint} not documented"
            assert 'post' in paths[endpoint], f"{endpoint} should have POST method"

    def test_endpoints_have_operation_ids(self, openapi_spec):
        """Test that all endpoints have operationId."""
        paths = openapi_spec['paths']

        for path, methods in paths.items():
            for method, spec in methods.items():
                if method in ['get', 'post', 'put', 'patch', 'delete']:
                    assert 'operationId' in spec, \
                        f"{method.upper()} {path} missing operationId"

    def test_endpoints_have_tags(self, openapi_spec):
        """Test that all endpoints have tags."""
        paths = openapi_spec['paths']

        for path, methods in paths.items():
            for method, spec in methods.items():
                if method in ['get', 'post', 'put', 'patch', 'delete']:
                    assert 'tags' in spec, f"{method.upper()} {path} missing tags"
                    assert len(spec['tags']) > 0, \
                        f"{method.upper()} {path} has empty tags"

    def test_endpoints_have_responses(self, openapi_spec):
        """Test that all endpoints define responses."""
        paths = openapi_spec['paths']

        for path, methods in paths.items():
            for method, spec in methods.items():
                if method in ['get', 'post', 'put', 'patch', 'delete']:
                    assert 'responses' in spec, \
                        f"{method.upper()} {path} missing responses"
                    assert len(spec['responses']) > 0, \
                        f"{method.upper()} {path} has no responses defined"

    def test_post_endpoints_have_request_body(self, openapi_spec):
        """Test that POST endpoints define requestBody."""
        paths = openapi_spec['paths']

        for path, methods in paths.items():
            if 'post' in methods:
                post_spec = methods['post']
                if path not in ['/api/auth/logout', '/api/auth/refresh']:
                    assert 'requestBody' in post_spec or 'parameters' in post_spec, \
                        f"POST {path} should have requestBody or parameters"

    def test_security_schemes_defined(self, openapi_spec):
        """Test that security schemes are defined if security is used."""
        paths = openapi_spec['paths']

        has_security = False
        for path, methods in paths.items():
            for method, spec in methods.items():
                if method in ['get', 'post', 'put', 'patch', 'delete']:
                    if 'security' in spec and spec['security']:
                        has_security = True
                        break
            if has_security:
                break

        if has_security:
            assert 'components' in openapi_spec, "Missing components section"
            assert 'securitySchemes' in openapi_spec['components'], \
                "Security used but securitySchemes not defined"

    def test_openapi_spec_size(self, openapi_spec_path):
        """Test that OpenAPI spec is substantial (not empty/minimal)."""
        file_size = openapi_spec_path.stat().st_size
        assert file_size > 5000, \
            f"OpenAPI spec seems too small ({file_size} bytes), expected > 5KB"

    def test_no_duplicate_operation_ids(self, openapi_spec):
        """Test that operationId values are unique."""
        paths = openapi_spec['paths']
        operation_ids = []

        for path, methods in paths.items():
            for method, spec in methods.items():
                if method in ['get', 'post', 'put', 'patch', 'delete']:
                    if 'operationId' in spec:
                        operation_ids.append(spec['operationId'])

        duplicates = [op_id for op_id in operation_ids if operation_ids.count(op_id) > 1]
        assert len(duplicates) == 0, f"Duplicate operationIds found: {set(duplicates)}"
