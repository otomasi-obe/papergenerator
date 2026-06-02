"""
Common JSONSchema Definitions
=====================================
Reusable schema components for API validation.
"""

PAPER_ID_PATTERN = r'^[a-zA-Z0-9_-]{1,50}$'
UUID_PATTERN = r'^[a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12}$'

PAGINATION_SCHEMA = {
    "type": "object",
    "properties": {
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 20
        },
        "offset": {
            "type": "integer",
            "minimum": 0,
            "default": 0
        }
    }
}

PAPER_ID_SCHEMA = {
    "type": "string",
    "pattern": PAPER_ID_PATTERN,
    "minLength": 1,
    "maxLength": 50
}

TITLE_SCHEMA = {
    "type": "string",
    "minLength": 1,
    "maxLength": 500
}

TIMESTAMP_SCHEMA = {
    "type": "string",
    "format": "date-time"
}

USER_ID_SCHEMA = {
    "type": "integer",
    "minimum": 1
}

BOOLEAN_SCHEMA = {
    "type": "boolean"
}

NON_EMPTY_STRING_SCHEMA = {
    "type": "string",
    "minLength": 1
}

OPTIONAL_STRING_SCHEMA = {
    "type": ["string", "null"]
}

POSITIVE_INTEGER_SCHEMA = {
    "type": "integer",
    "minimum": 1
}

NON_NEGATIVE_INTEGER_SCHEMA = {
    "type": "integer",
    "minimum": 0
}
