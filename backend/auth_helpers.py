"""
Authentication helper functions for secure user identity extraction.
Created by Bug Hunting Agent 4 - Security Audit.
"""
from flask_jwt_extended import get_jwt_identity
from flask import jsonify


def get_user_id_from_jwt() -> tuple[int | None, tuple | None]:
    """
    Safely extract user_id from JWT identity.
    
    Returns:
        (user_id, error_response) where error_response is None on success
        or a Flask response tuple on error.
    
    Example:
        user_id, error = get_user_id_from_jwt()
        if error:
            return error
        # use user_id safely
    """
    try:
        identity = get_jwt_identity()
        if identity is None:
            return None, (jsonify({"error": "Unauthorized"}), 401)
        user_id = int(identity)
        if user_id <= 0:
            return None, (jsonify({"error": "Invalid user identity"}), 401)
        return user_id, None
    except (ValueError, TypeError):
        return None, (jsonify({"error": "Invalid user identity"}), 401)
