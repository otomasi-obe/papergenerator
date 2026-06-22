"""
Tests for API Request Validation Middleware
=====================================
Comprehensive tests for validation decorators and error handling.
"""

import json

import pytest
from flask import Flask, jsonify, request

from utils.middleware.error_handler import format_validation_error
from utils.middleware.validation import validate_data, validate_query, validate_request


@pytest.fixture
def app():
    """Create test Flask app."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestValidateRequest:
    """Test @validate_request decorator."""

    def test_valid_request_body(self, app, client):
        """Test validation passes with valid request body."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "age": {"type": "integer", "minimum": 0}
            },
            "required": ["name"]
        }

        @app.route('/test', methods=['POST'])
        @validate_request(schema)
        def test_endpoint():
            data = request.get_json()
            return jsonify({"success": True, "data": data})

        response = client.post('/test',
                              json={"name": "John", "age": 30},
                              content_type='application/json')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['name'] == "John"

    def test_missing_required_field(self, app, client):
        """Test validation fails when required field is missing."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"}
            },
            "required": ["name", "email"]
        }

        @app.route('/test', methods=['POST'])
        @validate_request(schema)
        def test_endpoint():
            return jsonify({"success": True})

        response = client.post('/test',
                              json={"name": "John"},
                              content_type='application/json')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['error'] == 'Validation failed'
        assert len(data['details']) > 0
        assert any('email' in detail['field'] for detail in data['details'])

    def test_invalid_field_type(self, app, client):
        """Test validation fails when field type is wrong."""
        schema = {
            "type": "object",
            "properties": {
                "age": {"type": "integer"}
            }
        }

        @app.route('/test', methods=['POST'])
        @validate_request(schema)
        def test_endpoint():
            return jsonify({"success": True})

        response = client.post('/test',
                              json={"age": "not a number"},
                              content_type='application/json')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['error'] == 'Validation failed'
        assert any('type' in detail['type'] for detail in data['details'])

    def test_string_length_validation(self, app, client):
        """Test string length constraints."""
        schema = {
            "type": "object",
            "properties": {
                "username": {"type": "string", "minLength": 3, "maxLength": 20}
            }
        }

        @app.route('/test', methods=['POST'])
        @validate_request(schema)
        def test_endpoint():
            return jsonify({"success": True})

        response = client.post('/test',
                              json={"username": "ab"},
                              content_type='application/json')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert any('at least 3 characters' in detail['message']
                  for detail in data['details'])

    def test_number_range_validation(self, app, client):
        """Test number min/max constraints."""
        schema = {
            "type": "object",
            "properties": {
                "score": {"type": "integer", "minimum": 0, "maximum": 100}
            }
        }

        @app.route('/test', methods=['POST'])
        @validate_request(schema)
        def test_endpoint():
            return jsonify({"success": True})

        response = client.post('/test',
                              json={"score": 150},
                              content_type='application/json')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert any('at most 100' in detail['message']
                  for detail in data['details'])

    def test_enum_validation(self, app, client):
        """Test enum constraint."""
        schema = {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "inactive", "pending"]}
            }
        }

        @app.route('/test', methods=['POST'])
        @validate_request(schema)
        def test_endpoint():
            return jsonify({"success": True})

        response = client.post('/test',
                              json={"status": "invalid"},
                              content_type='application/json')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert any('must be one of' in detail['message']
                  for detail in data['details'])

    def test_empty_body_required(self, app, client):
        """Test validation fails when body is required but empty."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}}
        }

        @app.route('/test', methods=['POST'])
        @validate_request(schema, required=True)
        def test_endpoint():
            return jsonify({"success": True})

        response = client.post('/test', data='', content_type='application/json')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Request body is required' in data['message']

    def test_empty_body_optional(self, app, client):
        """Test validation passes when body is optional and empty."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}}
        }

        @app.route('/test', methods=['POST'])
        @validate_request(schema, required=False)
        def test_endpoint():
            return jsonify({"success": True})

        response = client.post('/test', data='', content_type='application/json')

        assert response.status_code == 200


class TestValidateQuery:
    """Test @validate_query decorator."""

    def test_valid_query_params(self, app, client):
        """Test validation passes with valid query parameters."""
        schema = {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0}
            }
        }

        @app.route('/test', methods=['GET'])
        @validate_query(schema)
        def test_endpoint():
            return jsonify({"success": True})

        response = client.get('/test?limit=10&offset=0')

        assert response.status_code == 200

    def test_invalid_query_param_type(self, app, client):
        """Test validation fails with invalid query param type."""
        schema = {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1}
            }
        }

        @app.route('/test', methods=['GET'])
        @validate_query(schema)
        def test_endpoint():
            return jsonify({"success": True})

        response = client.get('/test?limit=abc')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['error'] == 'Validation failed'

    def test_query_param_out_of_range(self, app, client):
        """Test validation fails when query param is out of range."""
        schema = {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100}
            }
        }

        @app.route('/test', methods=['GET'])
        @validate_query(schema)
        def test_endpoint():
            return jsonify({"success": True})

        response = client.get('/test?limit=200')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert any('at most 100' in detail['message']
                  for detail in data['details'])

    def test_boolean_query_param(self, app, client):
        """Test boolean query parameter conversion."""
        schema = {
            "type": "object",
            "properties": {
                "active": {"type": "boolean"}
            }
        }

        @app.route('/test', methods=['GET'])
        @validate_query(schema)
        def test_endpoint():
            return jsonify({"success": True})

        response = client.get('/test?active=true')
        assert response.status_code == 200

        response = client.get('/test?active=false')
        assert response.status_code == 200


class TestValidateData:
    """Test validate_data helper function."""

    def test_valid_data(self):
        """Test validation passes with valid data."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            },
            "required": ["name"]
        }

        is_valid, errors = validate_data({"name": "John"}, schema)

        assert is_valid is True
        assert errors is None

    def test_invalid_data(self):
        """Test validation fails with invalid data."""
        schema = {
            "type": "object",
            "properties": {
                "age": {"type": "integer"}
            },
            "required": ["age"]
        }

        is_valid, errors = validate_data({"age": "not a number"}, schema)

        assert is_valid is False
        assert errors is not None
        assert len(errors) > 0


class TestErrorFormatting:
    """Test error message formatting."""

    def test_format_validation_error(self, app):
        """Test error formatting produces consistent structure."""
        from jsonschema import Draft7Validator

        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            },
            "required": ["name"]
        }

        validator = Draft7Validator(schema)
        errors = list(validator.iter_errors({}))

        with app.app_context():
            response = format_validation_error(errors)
            data = json.loads(response.data)

            assert 'error' in data
            assert 'message' in data
            assert 'details' in data
            assert isinstance(data['details'], list)
            assert len(data['details']) > 0

            detail = data['details'][0]
            assert 'field' in detail
            assert 'message' in detail
            assert 'type' in detail
