"""
Integration tests for SSE Parser utility.

Tests the sse_parser module functions for parsing Server-Sent Events (SSE)
streams from chat endpoints.
"""

from tests.integration.sse_parser import (
    filter_events_by_type,
    get_event_sequence,
    parse_sse_stream,
    validate_sse_format,
)


class TestSSEParsing:
    """Test SSE Parser utility functions"""

    def test_parse_basic_sse_stream(self):
        """Test parsing a simple single-event SSE stream"""
        sse_data = b'event: text\ndata: {"content": "Hello"}\n\n'

        events = parse_sse_stream(sse_data)

        assert len(events) == 1
        assert events[0].event == "text"
        assert events[0].data == {"content": "Hello"}
        assert events[0].raw_data == '{"content": "Hello"}'

    def test_parse_multiple_events(self):
        """Test parsing a stream with multiple events"""
        sse_data = b'''event: text
data: {"content": "Hello"}

event: text
data: {"content": " World"}

event: done
data: {"message_id": 123}

'''

        events = parse_sse_stream(sse_data)

        assert len(events) == 3
        assert events[0].event == "text"
        assert events[0].data == {"content": "Hello"}
        assert events[1].event == "text"
        assert events[1].data == {"content": " World"}
        assert events[2].event == "done"
        assert events[2].data == {"message_id": 123}

        sequence = get_event_sequence(events)
        assert sequence == ["text", "text", "done"]

    def test_parse_json_data(self):
        """Test parsing SSE with complex nested JSON data"""
        sse_data = b'event: metadata\ndata: {"user_id": 1, "timestamp": "2024-01-01", "nested": {"key": "value"}}\n\n'

        events = parse_sse_stream(sse_data)

        assert len(events) == 1
        assert events[0].event == "metadata"
        assert isinstance(events[0].data, dict)
        assert events[0].data["user_id"] == 1
        assert events[0].data["timestamp"] == "2024-01-01"
        assert events[0].data["nested"]["key"] == "value"

    def test_filter_events_by_type(self):
        """Test filtering events by type"""
        sse_data = b'''event: text
data: {"content": "Hello"}

event: metadata
data: {"user_id": 1}

event: text
data: {"content": "World"}

event: done
data: {"message_id": 123}

'''

        events = parse_sse_stream(sse_data)

        text_events = filter_events_by_type(events, "text")
        assert len(text_events) == 2
        assert all(e.event == "text" for e in text_events)

        metadata_events = filter_events_by_type(events, "metadata")
        assert len(metadata_events) == 1
        assert metadata_events[0].event == "metadata"

        done_events = filter_events_by_type(events, "done")
        assert len(done_events) == 1
        assert done_events[0].event == "done"

        nonexistent_events = filter_events_by_type(events, "nonexistent")
        assert len(nonexistent_events) == 0

    def test_get_event_sequence(self):
        """Test getting event type sequence"""
        sse_data = b'''event: text
data: {"content": "A"}

event: text
data: {"content": "B"}

event: metadata
data: {"info": "test"}

event: done
data: {"id": 1}

'''

        events = parse_sse_stream(sse_data)
        sequence = get_event_sequence(events)

        assert sequence == ["text", "text", "metadata", "done"]
        assert len(sequence) == 4

    def test_validate_sse_format_valid(self):
        """Test SSE format validation with valid data"""
        valid_sse = b'event: text\ndata: {"content": "Hello"}\n\n'

        assert validate_sse_format(valid_sse) is True

        multiple_events = b'''event: text
data: {"content": "Hello"}

event: done
data: {"id": 1}

'''
        assert validate_sse_format(multiple_events) is True

    def test_validate_sse_format_invalid(self):
        """Test SSE format validation with invalid data"""
        empty_data = b''
        assert validate_sse_format(empty_data) is False

        plain_text = b'This is just plain text, not SSE format'
        assert validate_sse_format(plain_text) is False

        malformed_sse = b'event: text\nno data field here\n\n'
        assert validate_sse_format(malformed_sse) is False

    def test_parse_multiline_data(self):
        """Test parsing SSE with multiline data field"""
        sse_data = b'''event: text
data: Line 1
data: Line 2
data: Line 3

'''

        events = parse_sse_stream(sse_data)

        assert len(events) == 1
        assert events[0].event == "text"
        assert events[0].raw_data == "Line 1\nLine 2\nLine 3"
        assert "Line 1" in events[0].raw_data
        assert "Line 2" in events[0].raw_data
        assert "Line 3" in events[0].raw_data
