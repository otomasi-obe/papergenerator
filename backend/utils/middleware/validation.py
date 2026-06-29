"""
API Request Validation Middleware
=====================================
Provides decorators for validating Flask request data using JSONSchema.
"""

import functools
import logging
from typing import Any, Callable, Dict, Optional

from flask import jsonify, request
from jsonschema import Draft7Validator

from .error_handler import format_validation_error

log = logging.getLogger(__name__)


def validate_request(schema: Dict[str, Any], required: bool = True):
    """
    Decorator to validate request JSON body against a JSONSchema.

    Args:
        schema: JSONSchema definition for request body
        required: If True, request body is required (default: True)

    Returns:
        Decorated function that validates request before execution

    Example:
        @app.route('/api/papers', methods=['POST'])
        @validate_request(PAPER_CREATE_SCHEMA)
        def create_paper():
            data = request.get_json()
            # data is guaranteed to be valid here
            ...
    """
    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            data = request.get_json(silent=True)

            if data is None:
                if required:
                    return jsonify({
                        'error': 'Validation failed',
                        'message': 'Request body is required',
                        'details': []
                    }), 400
                return f(*args, **kwargs)

            validator = Draft7Validator(schema)
            errors = list(validator.iter_errors(data))

            if errors:
                return format_validation_error(errors), 400

            return f(*args, **kwargs)

        return wrapper
    return decorator


def validate_query(schema: Dict[str, Any]):
    """
    Decorator to validate query parameters against a JSONSchema.

    Args:
        schema: JSONSchema definition for query parameters

    Returns:
        Decorated function that validates query params before execution

    Example:
        @app.route('/api/papers', methods=['GET'])
        @validate_query(PAPER_LIST_QUERY_SCHEMA)
        def list_papers():
            limit = request.args.get('limit')
            # limit is guaranteed to be valid here
            ...
    """
    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            query_params = request.args.to_dict()

            for key, value in query_params.items():
                if value.isdigit():
                    query_params[key] = int(value)
                elif value.lower() in ('true', 'false'):
                    query_params[key] = value.lower() == 'true'

            validator = Draft7Validator(schema)
            errors = list(validator.iter_errors(query_params))

            if errors:
                return format_validation_error(errors), 400

            return f(*args, **kwargs)

        return wrapper
    return decorator

