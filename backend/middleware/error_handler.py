"""
Error Handler for Validation Middleware
=====================================
Formats validation errors into consistent API responses.
"""

from typing import Any, Dict, List

from flask import jsonify
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError


class ValidationError(Exception):
    """Custom validation error exception."""

    def __init__(self, message: str, details: List[Dict[str, Any]] = None):
        self.message = message
        self.details = details or []
        super().__init__(self.message)


def format_validation_error(errors: List[JSONSchemaValidationError]) -> tuple:
    """
    Format JSONSchema validation errors into consistent API response.

    Args:
        errors: List of JSONSchema validation errors

    Returns:
        Tuple of (response_dict, status_code)
    """
    error_details = []

    for error in errors:
        field_path = '.'.join(str(p) for p in error.path) if error.path else 'root'

        error_detail = {
            'field': field_path,
            'message': error.message,
            'type': error.validator
        }

        if error.validator == 'required':
            missing_field = error.message.split("'")[1] if "'" in error.message else 'unknown'
            error_detail['field'] = f"{field_path}.{missing_field}" if field_path != 'root' else missing_field
            error_detail['message'] = f"Field '{missing_field}' is required"

        elif error.validator == 'type':
            expected_type = error.validator_value
            error_detail['message'] = f"Field '{field_path}' must be of type {expected_type}"

        elif error.validator == 'minLength':
            min_length = error.validator_value
            error_detail['message'] = f"Field '{field_path}' must be at least {min_length} characters"

        elif error.validator == 'maxLength':
            max_length = error.validator_value
            error_detail['message'] = f"Field '{field_path}' must be at most {max_length} characters"

        elif error.validator == 'minimum':
            minimum = error.validator_value
            error_detail['message'] = f"Field '{field_path}' must be at least {minimum}"

        elif error.validator == 'maximum':
            maximum = error.validator_value
            error_detail['message'] = f"Field '{field_path}' must be at most {maximum}"

        elif error.validator == 'pattern':
            error_detail['message'] = f"Field '{field_path}' format is invalid"

        elif error.validator == 'enum':
            allowed_values = error.validator_value
            error_detail['message'] = f"Field '{field_path}' must be one of: {', '.join(map(str, allowed_values))}"

        error_details.append(error_detail)

    response = {
        'error': 'Validation failed',
        'message': f"Request validation failed with {len(error_details)} error(s)",
        'details': error_details
    }

    return jsonify(response)
