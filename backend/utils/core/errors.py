"""
Error Handling System
=====================
Unified error handling with standardized error codes, categories, and responses.

Error Categories:
- VALIDATION: Input validation failures (400)
- AUTH: Authentication/authorization failures (401/403)
- NOT_FOUND: Resource not found (404)
- CONFLICT: Resource conflicts, locks (409)
- RATE_LIMIT: Rate limiting (429)
- EXTERNAL: External API failures (502/503)
- SERVER: Internal server errors (500)
"""

import logging
from typing import Any, Dict, Optional

from flask import jsonify

log = logging.getLogger(__name__)


class ErrorCategory:
    VALIDATION = "VALIDATION"
    AUTH = "AUTH"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMIT = "RATE_LIMIT"
    EXTERNAL = "EXTERNAL"
    SERVER = "SERVER"


class ErrorCode:
    VALIDATION_FAILED = "VALIDATION_FAILED"
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_FIELD = "MISSING_FIELD"
    INVALID_FORMAT = "INVALID_FORMAT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    INVALID_FILE_TYPE = "INVALID_FILE_TYPE"

    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"

    NOT_FOUND = "NOT_FOUND"
    PAPER_NOT_FOUND = "PAPER_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    CONVERSATION_NOT_FOUND = "CONVERSATION_NOT_FOUND"

    PAPER_LOCKED = "PAPER_LOCKED"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    DUPLICATE_ENTRY = "DUPLICATE_ENTRY"

    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"

    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    EXTERNAL_API_ERROR = "EXTERNAL_API_ERROR"

    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"


ERROR_MESSAGES_ID = {
    ErrorCode.VALIDATION_FAILED: "Validasi gagal",
    ErrorCode.INVALID_INPUT: "Input tidak valid",
    ErrorCode.MISSING_FIELD: "Field wajib tidak ada",
    ErrorCode.INVALID_FORMAT: "Format tidak valid",
    ErrorCode.FILE_TOO_LARGE: "File terlalu besar",
    ErrorCode.INVALID_FILE_TYPE: "Tipe file tidak didukung",
    ErrorCode.UNAUTHORIZED: "Anda belum login",
    ErrorCode.FORBIDDEN: "Anda tidak memiliki akses",
    ErrorCode.TOKEN_EXPIRED: "Sesi Anda telah berakhir",
    ErrorCode.INVALID_CREDENTIALS: "Email atau password salah",
    ErrorCode.NOT_FOUND: "Data tidak ditemukan",
    ErrorCode.PAPER_NOT_FOUND: "Paper tidak ditemukan",
    ErrorCode.USER_NOT_FOUND: "User tidak ditemukan",
    ErrorCode.FILE_NOT_FOUND: "File tidak ditemukan",
    ErrorCode.CONVERSATION_NOT_FOUND: "Percakapan tidak ditemukan",
    ErrorCode.PAPER_LOCKED: "Paper sedang diproses",
    ErrorCode.RESOURCE_CONFLICT: "Konflik resource",
    ErrorCode.DUPLICATE_ENTRY: "Data sudah ada",
    ErrorCode.RATE_LIMIT_EXCEEDED: "Terlalu banyak request",
    ErrorCode.QUOTA_EXCEEDED: "Kuota Anda habis",
    ErrorCode.UPSTREAM_TIMEOUT: "AI sedang sibuk",
    ErrorCode.UPSTREAM_ERROR: "Layanan AI bermasalah",
    ErrorCode.EXTERNAL_API_ERROR: "Layanan eksternal bermasalah",
    ErrorCode.INTERNAL_ERROR: "Terjadi kesalahan sistem",
    ErrorCode.DATABASE_ERROR: "Kesalahan database",
    ErrorCode.TOOL_EXECUTION_FAILED: "Eksekusi tool gagal",
}


class AppError(Exception):
    def __init__(
        self,
        message: str,
        code: str = ErrorCode.INTERNAL_ERROR,
        category: str = ErrorCategory.SERVER,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
        user_message: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.category = category
        self.status_code = status_code
        self.details = details or {}
        self.user_message = user_message or ERROR_MESSAGES_ID.get(code, message)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "error": self.user_message,
            "code": self.code,
            "category": self.category,
        }
        if self.details:
            result["details"] = self.details
        return result


class ValidationError(AppError):
    def __init__(
        self, message: str, code: str = ErrorCode.VALIDATION_FAILED, details: Optional[Dict] = None
    ):
        super().__init__(
            message=message,
            code=code,
            category=ErrorCategory.VALIDATION,
            status_code=400,
            details=details,
        )


class AuthError(AppError):
    def __init__(self, message: str, code: str = ErrorCode.UNAUTHORIZED, status_code: int = 401):
        super().__init__(
            message=message,
            code=code,
            category=ErrorCategory.AUTH,
            status_code=status_code,
        )


class NotFoundError(AppError):
    def __init__(
        self, message: str, code: str = ErrorCode.NOT_FOUND, resource_type: Optional[str] = None
    ):
        details = {"resource_type": resource_type} if resource_type else None
        super().__init__(
            message=message,
            code=code,
            category=ErrorCategory.NOT_FOUND,
            status_code=404,
            details=details,
        )


class ConflictError(AppError):
    def __init__(
        self, message: str, code: str = ErrorCode.RESOURCE_CONFLICT, details: Optional[Dict] = None
    ):
        super().__init__(
            message=message,
            code=code,
            category=ErrorCategory.CONFLICT,
            status_code=409,
            details=details,
        )


class RateLimitError(AppError):
    def __init__(
        self,
        message: str,
        code: str = ErrorCode.RATE_LIMIT_EXCEEDED,
        retry_after: Optional[int] = None,
    ):
        details = {"retry_after": retry_after} if retry_after else None
        super().__init__(
            message=message,
            code=code,
            category=ErrorCategory.RATE_LIMIT,
            status_code=429,
            details=details,
        )


class ExternalError(AppError):
    def __init__(
        self,
        message: str,
        code: str = ErrorCode.EXTERNAL_API_ERROR,
        status_code: int = 502,
        service: Optional[str] = None,
    ):
        details = {"service": service} if service else None
        super().__init__(
            message=message,
            code=code,
            category=ErrorCategory.EXTERNAL,
            status_code=status_code,
            details=details,
        )



