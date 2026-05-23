"""
Error Handling Examples
=======================
Examples showing how to use the new error handling system.
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from core.errors import (
    ValidationError, AuthError, NotFoundError, ConflictError,
    RateLimitError, ExternalError, ErrorCode, ErrorCategory
)
from models import db, Paper, User

examples_bp = Blueprint('examples', __name__)


@examples_bp.route('/api/examples/validation', methods=['POST'])
@jwt_required()
def example_validation():
    """Example: Input validation with detailed error messages."""
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            code=ErrorCode.MISSING_FIELD,
            details={"field": "body"}
        )
    
    title = data.get('title', '').strip()
    if not title:
        raise ValidationError(
            message="Title is required",
            code=ErrorCode.MISSING_FIELD,
            details={"field": "title"}
        )
    
    if len(title) > 200:
        raise ValidationError(
            message="Title is too long",
            code=ErrorCode.INVALID_INPUT,
            details={"field": "title", "max_length": 200, "actual_length": len(title)}
        )
    
    return jsonify({"message": "Validation passed", "title": title})


@examples_bp.route('/api/examples/papers/<paper_id>', methods=['GET'])
@jwt_required()
def example_not_found(paper_id):
    """Example: Resource not found with proper error code."""
    user_id = get_jwt_identity()
    
    if not paper_id or len(paper_id) > 20:
        raise ValidationError(
            message="Invalid paper ID format",
            code=ErrorCode.INVALID_FORMAT,
            details={"field": "paper_id", "max_length": 20}
        )
    
    paper = Paper.query.get(paper_id)
    if not paper:
        raise NotFoundError(
            message=f"Paper {paper_id} not found",
            code=ErrorCode.PAPER_NOT_FOUND,
            resource_type="paper"
        )
    
    if paper.user_id != user_id:
        raise AuthError(
            message="You don't have access to this paper",
            code=ErrorCode.FORBIDDEN,
            status_code=403
        )
    
    return jsonify(paper.to_dict())


@examples_bp.route('/api/examples/papers/<paper_id>/generate', methods=['POST'])
@jwt_required()
def example_conflict(paper_id):
    """Example: Resource conflict (paper locked)."""
    user_id = get_jwt_identity()
    
    paper = Paper.query.get(paper_id)
    if not paper:
        raise NotFoundError(
            message=f"Paper {paper_id} not found",
            code=ErrorCode.PAPER_NOT_FOUND
        )
    
    if paper.user_id != user_id:
        raise AuthError(
            message="Access denied",
            code=ErrorCode.FORBIDDEN,
            status_code=403
        )
    
    if paper.active_operation:
        raise ConflictError(
            message=f"Paper is locked by {paper.active_operation}",
            code=ErrorCode.PAPER_LOCKED,
            details={
                "paper_id": paper_id,
                "active_operation": paper.active_operation,
                "started_at": paper.active_operation_started_at.isoformat() if paper.active_operation_started_at else None
            }
        )
    
    return jsonify({"message": "Generation started"})


@examples_bp.route('/api/examples/quota-check', methods=['GET'])
@jwt_required()
def example_quota():
    """Example: Quota exceeded error."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if not user:
        raise NotFoundError(
            message="User not found",
            code=ErrorCode.USER_NOT_FOUND
        )
    
    if user.token_used_month >= user.token_quota_monthly:
        raise RateLimitError(
            message="Monthly token quota exceeded",
            code=ErrorCode.QUOTA_EXCEEDED,
            retry_after=None
        )
    
    return jsonify({
        "quota": user.token_quota_monthly,
        "used": user.token_used_month,
        "remaining": user.token_quota_monthly - user.token_used_month
    })


@examples_bp.route('/api/examples/external-api', methods=['POST'])
@jwt_required()
def example_external_error():
    """Example: External API error handling."""
    import requests
    
    try:
        response = requests.post(
            "https://api.example.com/generate",
            json={"prompt": "test"},
            timeout=30
        )
        response.raise_for_status()
        return jsonify(response.json())
    
    except requests.Timeout:
        raise ExternalError(
            message="AI service timeout after 30 seconds",
            code=ErrorCode.UPSTREAM_TIMEOUT,
            status_code=503,
            service="AI Generation API"
        )
    
    except requests.RequestException as e:
        raise ExternalError(
            message=f"AI service error: {str(e)}",
            code=ErrorCode.UPSTREAM_ERROR,
            status_code=502,
            service="AI Generation API"
        )


@examples_bp.route('/api/examples/database-error', methods=['GET'])
@jwt_required()
def example_database_error():
    """Example: Database error handling."""
    from core.errors import AppError
    
    try:
        papers = Paper.query.all()
        return jsonify([p.to_dict() for p in papers])
    
    except Exception as e:
        import logging
        log = logging.getLogger(__name__)
        log.exception("Database query failed")
        
        raise AppError(
            message="Database operation failed",
            code=ErrorCode.DATABASE_ERROR,
            category=ErrorCategory.SERVER,
            status_code=500,
            details={"operation": "query_all_papers"}
        )


@examples_bp.route('/api/examples/custom-error', methods=['POST'])
@jwt_required()
def example_custom_error():
    """Example: Custom error class."""
    from core.errors import AppError
    
    class FileProcessingError(AppError):
        def __init__(self, filename: str, reason: str):
            super().__init__(
                message=f"Failed to process file {filename}: {reason}",
                code="FILE_PROCESSING_FAILED",
                category=ErrorCategory.SERVER,
                status_code=500,
                details={
                    "filename": filename,
                    "reason": reason
                },
                user_message=f"Gagal memproses file {filename}"
            )
    
    data = request.get_json()
    filename = data.get('filename')
    
    if not filename:
        raise ValidationError(
            message="Filename is required",
            code=ErrorCode.MISSING_FIELD
        )
    
    if not filename.endswith('.pdf'):
        raise FileProcessingError(filename, "Only PDF files are supported")
    
    return jsonify({"message": "File processed successfully"})
