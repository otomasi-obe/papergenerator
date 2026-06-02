"""
SSE (Server-Sent Events) Parser Utility for Integration Tests

Parses SSE response streams from chat endpoints into structured events.
"""

import json
from dataclasses import dataclass
from typing import Any, List


@dataclass
class SSEEvent:
    """Represents a single SSE event"""
    event: str
    data: Any
    raw_data: str = ""

    def __post_init__(self):
        if isinstance(self.data, str):
            try:
                self.data = json.loads(self.data)
            except (json.JSONDecodeError, ValueError):
                pass


def parse_sse_stream(response_data: bytes) -> List[SSEEvent]:
    """
    Parse SSE stream into list of SSEEvent objects.

    SSE Format:
        event: text
        data: {"content": "Hello"}

        event: done
        data: {"message_id": 123}

    Args:
        response_data: Raw bytes from SSE response

    Returns:
        List of SSEEvent objects
    """
    events = []
    lines = response_data.decode('utf-8').split('\n')

    current_event = None
    current_data_lines = []

    for line in lines:
        line = line.rstrip('\r')

        if line.startswith('event:'):
            current_event = line[6:].strip()

        elif line.startswith('data:'):
            data_content = line[5:].strip()
            current_data_lines.append(data_content)

        elif line == '':
            if current_event and current_data_lines:
                raw_data = '\n'.join(current_data_lines)
                events.append(SSEEvent(
                    event=current_event,
                    data=raw_data,
                    raw_data=raw_data
                ))
                current_event = None
                current_data_lines = []

    return events


def filter_events_by_type(events: List[SSEEvent], event_type: str) -> List[SSEEvent]:
    """Filter events by type"""
    return [e for e in events if e.event == event_type]


def get_event_sequence(events: List[SSEEvent]) -> List[str]:
    """Get sequence of event types"""
    return [e.event for e in events]


def validate_sse_format(response_data: bytes) -> bool:
    """
    Validate that response follows SSE format.

    Returns:
        True if valid SSE format, False otherwise
    """
    try:
        events = parse_sse_stream(response_data)
        return len(events) > 0
    except Exception:
        return False
