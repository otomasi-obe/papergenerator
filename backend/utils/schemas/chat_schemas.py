"""
Chat API JSONSchema Definitions
=====================================
Validation schemas for chat-related endpoints.
"""

from .common_schemas import BOOLEAN_SCHEMA, NON_EMPTY_STRING_SCHEMA, OPTIONAL_STRING_SCHEMA

CHAT_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "message": NON_EMPTY_STRING_SCHEMA,
        "conversation_id": OPTIONAL_STRING_SCHEMA,
        "paper_id": OPTIONAL_STRING_SCHEMA,
        "mode": {
            "type": "string",
            "enum": ["chat", "generate", "refine", "research"]
        },
        "stream": BOOLEAN_SCHEMA,
        "context": {
            "type": "object",
            "properties": {
                "section": {"type": "string"},
                "previous_messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {
                                "type": "string",
                                "enum": ["user", "assistant", "system"]
                            },
                            "content": NON_EMPTY_STRING_SCHEMA
                        },
                        "required": ["role", "content"]
                    }
                }
            }
        }
    },
    "required": ["message"]
}

CONVERSATION_CREATE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
        },
        "paper_id": OPTIONAL_STRING_SCHEMA
    },
    "required": ["title"]
}

CONVERSATION_LIST_QUERY_SCHEMA = {
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
        "paper_id": {"type": "string"}
    }
}
