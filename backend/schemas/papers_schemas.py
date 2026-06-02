"""
Paper API JSONSchema Definitions
=====================================
Validation schemas for paper-related endpoints.
"""

from .common_schemas import (
    NON_EMPTY_STRING_SCHEMA,
    OPTIONAL_STRING_SCHEMA,
    PAPER_ID_SCHEMA,
    TITLE_SCHEMA,
)

PAPER_CREATE_TITLE_SCHEMA = {
    "type": "string",
    "minLength": 0,
    "maxLength": 500
}

PAPER_CREATE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": PAPER_ID_SCHEMA,
        "title": PAPER_CREATE_TITLE_SCHEMA,
        "data": {
            "type": "object",
            "properties": {
                "title": PAPER_CREATE_TITLE_SCHEMA,
                "abstract": OPTIONAL_STRING_SCHEMA,
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": NON_EMPTY_STRING_SCHEMA,
                            "content": {"type": "string"}
                        }
                    }
                },
                "references": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": NON_EMPTY_STRING_SCHEMA,
                            "authors": {"type": "string"},
                            "year": {"type": ["integer", "string"]},
                            "venue": {"type": "string"}
                        }
                    }
                }
            }
        }
    }
}

PAPER_UPDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": TITLE_SCHEMA,
        "data": {
            "type": "object"
        }
    }
}

PAPER_LIST_QUERY_SCHEMA = {
    "type": "object",
    "properties": {
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100
        },
        "offset": {
            "type": "integer",
            "minimum": 0
        },
        "search": {
            "type": "string",
            "minLength": 1
        }
    }
}

PAPER_PATCH_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["add", "remove", "replace", "move", "copy", "test"]
            },
            "path": {
                "type": "string",
                "pattern": "^/"
            },
            "value": {}
        },
        "required": ["op", "path"]
    },
    "minItems": 1
}
