"""
Unit tests for core/errors.py — Error handling system.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

os.environ.setdefault("FLASK_ENV", "testing")

try:
    from utils.core.errors import (
        AppError,
        AuthError,
        ConflictError,
        ErrorCategory,
        ErrorCode,
        ExternalError,
        NotFoundError,
        RateLimitError,
        ValidationError,
        sanitize_error_message,
    )
except Exception as e:
    pytest.skip(f"Errors module bootstrap failed: {e}", allow_module_level=True)


def test_app_error_basic():
    error = AppError(
        message="Test error",
        code=ErrorCode.INTERNAL_ERROR,
        category=ErrorCategory.SERVER,
        status_code=500
    )

    assert error.message == "Test error"
    assert error.code == ErrorCode.INTERNAL_ERROR
    assert error.category == ErrorCategory.SERVER
    assert error.status_code == 500


def test_app_error_to_dict():
    error = AppError(
        message="Test error",
        code=ErrorCode.INTERNAL_ERROR,
        category=ErrorCategory.SERVER,
        status_code=500,
        details={"field": "value"}
    )

    result = error.to_dict()

    assert "error" in result
    assert result["code"] == ErrorCode.INTERNAL_ERROR
    assert result["category"] == ErrorCategory.SERVER
    assert result["details"]["field"] == "value"


def test_validation_error():
    error = ValidationError(
        message="Invalid input",
        code=ErrorCode.INVALID_INPUT,
        details={"field": "email"}
    )

    assert error.category == ErrorCategory.VALIDATION
    assert error.status_code == 400
    assert error.code == ErrorCode.INVALID_INPUT
    assert error.details["field"] == "email"


def test_auth_error_unauthorized():
    error = AuthError(
        message="Not authenticated",
        code=ErrorCode.UNAUTHORIZED,
        status_code=401
    )

    assert error.category == ErrorCategory.AUTH
    assert error.status_code == 401
    assert error.code == ErrorCode.UNAUTHORIZED


def test_auth_error_forbidden():
    error = AuthError(
        message="Access denied",
        code=ErrorCode.FORBIDDEN,
        status_code=403
    )

    assert error.category == ErrorCategory.AUTH
    assert error.status_code == 403
    assert error.code == ErrorCode.FORBIDDEN


def test_not_found_error():
    error = NotFoundError(
        message="Paper not found",
        code=ErrorCode.PAPER_NOT_FOUND,
        resource_type="paper"
    )

    assert error.category == ErrorCategory.NOT_FOUND
    assert error.status_code == 404
    assert error.code == ErrorCode.PAPER_NOT_FOUND
    assert error.details["resource_type"] == "paper"


def test_conflict_error():
    error = ConflictError(
        message="Paper is locked",
        code=ErrorCode.PAPER_LOCKED,
        details={"locked_by": "user123"}
    )

    assert error.category == ErrorCategory.CONFLICT
    assert error.status_code == 409
    assert error.code == ErrorCode.PAPER_LOCKED
    assert error.details["locked_by"] == "user123"


def test_rate_limit_error():
    error = RateLimitError(
        message="Too many requests",
        code=ErrorCode.RATE_LIMIT_EXCEEDED,
        retry_after=60
    )

    assert error.category == ErrorCategory.RATE_LIMIT
    assert error.status_code == 429
    assert error.code == ErrorCode.RATE_LIMIT_EXCEEDED
    assert error.details["retry_after"] == 60


def test_external_error():
    error = ExternalError(
        message="OpenAI API failed",
        code=ErrorCode.EXTERNAL_API_ERROR,
        status_code=502,
        service="openai"
    )

    assert error.category == ErrorCategory.EXTERNAL
    assert error.status_code == 502
    assert error.code == ErrorCode.EXTERNAL_API_ERROR
    assert error.details["service"] == "openai"


def test_sanitize_error_message_sql():
    raw = "psycopg2.errors.UndefinedTable: relation 'users' does not exist"
    sanitized = sanitize_error_message(raw)
    assert sanitized == "Terjadi kesalahan sistem"


def test_sanitize_error_message_traceback():
    raw = 'Traceback (most recent call last):\n  File "app.py", line 123'
    sanitized = sanitize_error_message(raw)
    assert sanitized == "Terjadi kesalahan sistem"


def test_sanitize_error_message_long():
    raw = "A" * 300
    sanitized = sanitize_error_message(raw)
    assert len(sanitized) <= 241
    assert sanitized.endswith("…")


def test_sanitize_error_message_safe():
    raw = "Invalid email format"
    sanitized = sanitize_error_message(raw)
    assert sanitized == "Invalid email format"


def test_error_user_message_indonesian():
    error = ValidationError(
        message="Validation failed",
        code=ErrorCode.VALIDATION_FAILED
    )

    assert "Validasi gagal" in error.user_message


def test_error_custom_user_message():
    error = AppError(
        message="Internal error",
        code=ErrorCode.INTERNAL_ERROR,
        user_message="Custom message for user"
    )

    assert error.user_message == "Custom message for user"


def test_quota_exceeded_error():
    error = RateLimitError(
        message="Monthly quota exceeded",
        code=ErrorCode.QUOTA_EXCEEDED,
        retry_after=2592000
    )

    assert error.code == ErrorCode.QUOTA_EXCEEDED
    assert error.category == ErrorCategory.RATE_LIMIT
    assert "Kuota Anda habis" in error.user_message
