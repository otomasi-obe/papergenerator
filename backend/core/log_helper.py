"""
Centralized Logging Helper
===========================
Provides structured logging utilities with context (user_id, paper_id, request_id).

Usage:
    from log_helper import get_logger, log_context
    
    log = get_logger(__name__)
    
    # Simple logging
    log.info("Paper created", paper_id=123, user_id=456)
    
    # With context manager
    with log_context(user_id=456, paper_id=123):
        log.info("Processing paper")  # Automatically includes user_id and paper_id
"""
import logging
import contextvars
from typing import Any, Dict, Optional
from flask import g, has_request_context

_log_context = contextvars.ContextVar('log_context', default={})


class ContextLogger(logging.LoggerAdapter):
    """
    Logger adapter that automatically includes context variables in log records.
    """
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        extra = kwargs.get('extra', {})
        
        ctx = _log_context.get()
        extra.update(ctx)
        
        if has_request_context():
            if hasattr(g, '_req_id'):
                extra['req_id'] = g._req_id
            if hasattr(g, 'user_id'):
                extra['user_id'] = g.user_id
        
        kwargs['extra'] = extra
        return msg, kwargs


def get_logger(name: str) -> ContextLogger:
    """
    Get a logger with automatic context injection.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        ContextLogger instance
    """
    base_logger = logging.getLogger(name)
    return ContextLogger(base_logger, {})


class log_context:
    """
    Context manager for setting log context variables.
    
    Usage:
        with log_context(user_id=123, paper_id=456):
            log.info("Processing")  # Includes user_id and paper_id
    """
    
    def __init__(self, **kwargs):
        self.context = kwargs
        self.token = None
    
    def __enter__(self):
        current = _log_context.get()
        new_context = {**current, **self.context}
        self.token = _log_context.set(new_context)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.token:
            _log_context.reset(self.token)


def set_log_context(**kwargs):
    """
    Set log context variables for the current context.
    
    Args:
        **kwargs: Context variables to set (user_id, paper_id, etc.)
    """
    current = _log_context.get()
    new_context = {**current, **kwargs}
    _log_context.set(new_context)


def clear_log_context():
    """Clear all log context variables."""
    _log_context.set({})


def log_performance(log: logging.Logger, operation: str, duration_ms: float, threshold_ms: float = 1000):
    """
    Log performance metrics with automatic slow operation detection.
    
    Args:
        log: Logger instance
        operation: Operation name
        duration_ms: Duration in milliseconds
        threshold_ms: Threshold for slow operation warning
    """
    extra = {
        'operation': operation,
        'duration_ms': round(duration_ms, 2),
        'threshold_ms': threshold_ms
    }
    
    if duration_ms > threshold_ms:
        log.warning(f"Slow operation: {operation}", extra=extra)
    else:
        log.debug(f"Performance: {operation}", extra=extra)


def log_error_with_context(log: logging.Logger, error: Exception, context: Optional[Dict[str, Any]] = None):
    """
    Log an error with additional context.
    
    Args:
        log: Logger instance
        error: Exception to log
        context: Additional context dictionary
    """
    extra = {
        'error_type': type(error).__name__,
        'error_msg': str(error),
    }
    
    if context:
        extra.update(context)
    
    log.exception(f"Error: {error}", extra=extra)
