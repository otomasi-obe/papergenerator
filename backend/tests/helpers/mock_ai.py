"""
AI Response Mocking for Testing

This module provides mock AI responses for testing rate limiting and other
functionality without making real API calls to AI services.

Usage:
    Set environment variable: MOCK_AI_RESPONSES=1

    from tests.helpers.mock_ai import should_mock_ai, get_mock_generate_response

    if should_mock_ai():
        return get_mock_generate_response()
"""

import os
import time
import uuid


def should_mock_ai():
    """Check if AI responses should be mocked."""
    return os.getenv('MOCK_AI_RESPONSES') == '1'


def get_mock_generate_response(prompt="test prompt", section="introduction"):
    """
    Get mock response for /api/generate endpoint.

    Returns response in the same format as real AI call:
    {
        "success": True,
        "content": "...",
        "text": "...",
        "model": "mock-model",
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    }
    """
    mock_content = f"""This is a mock response for testing purposes.

Section: {section}
Prompt: {prompt[:50]}...

This response is generated instantly without calling real AI services.
It maintains the same structure as real responses for testing rate limiting,
error handling, and other functionality.

Mock generated at: {time.time()}
"""

    return {
        "success": True,
        "content": mock_content,
        "text": mock_content,
        "model": "mock-v-opus",
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    }


def get_mock_generate_full_response(prompt="test prompt", job_id=None):
    """
    Get mock response for /api/generate-full endpoint.

    Returns job_id for background job tracking.
    """
    if job_id is None:
        job_id = str(uuid.uuid4())

    return {
        "success": True,
        "job_id": job_id,
        "message": "Mock paper generation started",
        "status": "processing"
    }


def get_mock_paper_content():
    """
    Get mock full paper content for completed jobs.

    Returns a complete paper structure with all sections.
    """
    return {
        "title": "Mock Research Paper for Testing",
        "abstract": "This is a mock abstract generated for testing purposes. It contains placeholder content that matches the structure of real papers.",
        "sections": {
            "introduction": "Mock introduction content with proper academic structure.",
            "methodology": "Mock methodology describing the research approach.",
            "results": "Mock results section with findings and analysis.",
            "discussion": "Mock discussion interpreting the results.",
            "conclusion": "Mock conclusion summarizing the research."
        },
        "references": [
            "[1] Mock Author et al., 'Mock Paper Title', Mock Journal, 2024.",
            "[2] Test Researcher, 'Testing Methodology', Test Conference, 2024."
        ],
        "metadata": {
            "generated_at": time.time(),
            "model": "mock-v-opus",
            "word_count": 500,
            "is_mock": True
        }
    }


def get_mock_upload_response(filename="test.pdf"):
    """
    Get mock response for file upload endpoints.

    Returns success response without actually processing files.
    """
    return {
        "success": True,
        "message": f"Mock upload successful: {filename}",
        "file_id": str(uuid.uuid4()),
        "filename": filename,
        "size": 1024,
        "processed": True
    }
