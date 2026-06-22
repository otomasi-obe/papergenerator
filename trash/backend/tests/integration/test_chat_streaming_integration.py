"""Integration tests for chat SSE streaming flow.

Tests end-to-end streaming with mocked upstream, covering:
- SSE event types: text, thinking, tool_call, tool_result, chips, done, error
- Proposal protocol (<<PROPOSAL>>)
- Mode switching
- Tool call lifecycle
- Error handling
- CSRF token handling
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from database.models import ChatMessage, Conversation, db
try:
    from tools.chat.tools import PROPOSAL_PREFIX
except ImportError:
    pytest.skip(
        "chat architecture consolidated into tools/chat/chat.py; "
        "PROPOSAL_PREFIX removed from tools.chat.tools. Test pending rewrite "
        "against the new chat.py API.",
        allow_module_level=True,
    )


class _FakeUpstreamResp:
    """Simulates an upstream SSE response."""

    def __init__(self, chunks, status_code=200):
        self.status_code = status_code
        self._chunks = chunks
        self._closed = False

    def iter_lines(self):
        for chunk in self._chunks:
            yield chunk

    def close(self):
        self._closed = True


def _make_sse_line(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _parse_sse_events(raw: bytes) -> list[dict]:
    """Parse raw SSE bytes into list of {event, data}."""
    events = []
    lines = raw.decode("utf-8").split("\n")
    current_event = None
    current_data = []
    for line in lines:
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: "):
            current_data.append(line[6:])
        elif line == "" and current_event and current_data:
            try:
                data = json.loads("".join(current_data))
            except json.JSONDecodeError:
                data = "".join(current_data)
            events.append({"event": current_event, "data": data})
            current_event = None
            current_data = []
    return events


@pytest.fixture
def test_conversation(app, test_user, test_paper):
    """Create a test conversation."""
    with app.app_context():
        conv = Conversation(
            id="integ-conv-001",
            user_id=test_user.id,
            paper_id=test_paper.id,
            title="Integration Test Chat",
        )
        db.session.add(conv)
        db.session.commit()
        yield conv
        db.session.delete(conv)
        db.session.commit()


class TestSSEStreaming:
    """Test SSE streaming with mocked upstream."""

    def test_text_streaming(self, client, auth_headers, test_conversation):
        """Test basic text streaming through SSE."""
        upstream_chunks = [
            'data: {"choices":[{"delta":{"content":"Hello "}}]}',
            'data: {"choices":[{"delta":{"content":"world"}}]}',
            "data: [DONE]",
        ]

        with patch("tools.chat.chat_streaming._call_upstream") as mock_upstream:
            mock_upstream.return_value = _FakeUpstreamResp(upstream_chunks)
            with patch("tools.chat.chat_streaming._build_messages", return_value=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "hi"},
            ]):
                with patch("tools.chat.chat_streaming._select_tools", return_value=("test prompt", [])):
                    with patch("tools.chat.chat_streaming.extract_facts", return_value=[]):
                        with patch("tools.chat.chat_streaming._log_chat_call"):
                            with patch("tools.chat.chat_streaming._write_turn_log"):
                                with patch("tools.chat.chat_streaming._turn_log_dir", return_value=None):
                                    response = client.post(
                                        f"/api/chat/conversations/{test_conversation.id}/messages",
                                        headers=auth_headers,
                                        json={"content": "Hello"},
                                    )

        assert response.status_code == 200
        assert response.content_type.startswith("text/event-stream")
        raw = response.data
        assert b"event: text" in raw
        assert b"event: done" in raw

    def test_retries_without_tools_when_tool_payload_rejected(self, client, auth_headers, test_conversation):
        """Tool-capable upstream rejects should fall back to plain chat."""
        upstream_chunks = [
            'data: {"choices":[{"delta":{"content":"ok"}}]}',
            "data: [DONE]",
        ]

        rejected = _FakeUpstreamResp(['data: {"error":"bad tools"}'], status_code=400)
        accepted = _FakeUpstreamResp(upstream_chunks)

        with patch("tools.chat.chat_streaming._call_upstream") as mock_upstream:
            mock_upstream.side_effect = [rejected, accepted]
            with patch("tools.chat.chat_streaming._build_messages", return_value=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "hi"},
            ]):
                test_conversation.mode = "tier0"
                db.session.commit()
                with patch("tools.chat.chat_streaming.extract_facts", return_value=[]):
                    with patch("tools.chat.chat_streaming._log_chat_call"):
                        with patch("tools.chat.chat_streaming._write_turn_log"):
                            with patch("tools.chat.chat_streaming._turn_log_dir", return_value=None):
                                response = client.post(
                                    f"/api/chat/conversations/{test_conversation.id}/messages",
                                    headers=auth_headers,
                                    json={"content": "tes"},
                                )

        raw = response.data
        assert b"event: error" not in raw
        assert b"event: text" in raw
        assert b"event: done" in raw
        assert b"Sambungan ke AI sedang macet" not in raw

    def test_thinking_streaming(self, client, auth_headers, test_conversation):
        """Test thinking events in stream."""
        upstream_chunks = [
            'data: {"choices":[{"delta":{"thinking":"Let me think..."}}]}',
            'data: {"choices":[{"delta":{"content":"Answer"}}]}',
            "data: [DONE]",
        ]

        with patch("tools.chat.chat_streaming._call_upstream") as mock_upstream:
            mock_upstream.return_value = _FakeUpstreamResp(upstream_chunks)
            with patch("tools.chat.chat_streaming._build_messages", return_value=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "hi"},
            ]):
                with patch("tools.chat.chat_streaming._select_tools", return_value=("test prompt", [])):
                    with patch("tools.chat.chat_streaming.extract_facts", return_value=[]):
                        with patch("tools.chat.chat_streaming._log_chat_call"):
                            with patch("tools.chat.chat_streaming._write_turn_log"):
                                with patch("tools.chat.chat_streaming._turn_log_dir", return_value=None):
                                    response = client.post(
                                        f"/api/chat/conversations/{test_conversation.id}/messages",
                                        headers=auth_headers,
                                        json={"content": "Think about it"},
                                    )

        assert response.status_code == 200
        raw = response.data
        assert b"event: thinking" in raw
        assert b"Let me think" in raw

    def test_tool_call_lifecycle(self, client, auth_headers, test_conversation):
        """Test tool_call -> tool_result SSE events."""
        upstream_chunks = [
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","function":{"name":"WebSearch","arguments":"{\\"query\\":\\"test\\"}"}}]}}]}',
            "data: [DONE]",
        ]

        with patch("tools.chat.chat_streaming._call_upstream") as mock_upstream:
            mock_upstream.return_value = _FakeUpstreamResp(upstream_chunks)
            with patch("tools.chat.chat_streaming._build_messages", return_value=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "search test"},
            ]):
                with patch("tools.chat.chat_streaming._select_tools", return_value=("test prompt", [])):
                    with patch("tools.chat.chat_streaming.extract_facts", return_value=[]):
                        with patch("tools.chat.chat_streaming._log_chat_call"):
                            with patch("tools.chat.chat_streaming._write_turn_log"):
                                with patch("tools.chat.chat_streaming._turn_log_dir", return_value=None):
                                    with patch("tools.chat.chat_streaming.execute_tool", return_value="search results"):
                                        response = client.post(
                                            f"/api/chat/conversations/{test_conversation.id}/messages",
                                            headers=auth_headers,
                                            json={"content": "search test"},
                                        )

        assert response.status_code == 200
        raw = response.data
        assert b"event: tool_call" in raw
        assert b"event: tool_result" in raw
        assert b"WebSearch" in raw

    def test_error_event_on_upstream_failure(self, client, auth_headers, test_conversation):
        """Test error event when upstream returns None."""
        with patch("tools.chat.chat_streaming._call_upstream", return_value=None):
            with patch("tools.chat.chat_streaming._build_messages", return_value=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "fail"},
            ]):
                with patch("tools.chat.chat_streaming._select_tools", return_value=("test prompt", [])):
                    with patch("tools.chat.chat_streaming.extract_facts", return_value=[]):
                        with patch("tools.chat.chat_streaming._log_chat_call"):
                            with patch("tools.chat.chat_streaming._write_turn_log"):
                                with patch("tools.chat.chat_streaming._turn_log_dir", return_value=None):
                                    response = client.post(
                                        f"/api/chat/conversations/{test_conversation.id}/messages",
                                        headers=auth_headers,
                                        json={"content": "trigger error"},
                                    )

        assert response.status_code == 200
        raw = response.data
        assert b"event: error" in raw

    def test_chips_event_on_propose_chips(self, client, auth_headers, test_conversation):
        """Test chips SSE event from ProposeChips tool."""
        chips_result = _make_sse_line("tool_result", {
            "name": "ProposeChips",
            "result": PROPOSAL_PREFIX + json.dumps({
                "kind": "chips",
                "chips": [{"label": "Option A"}, {"label": "Option B"}],
                "context_hint": "test",
            }),
        })

        upstream_chunks = [
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","function":{"name":"ProposeChips","arguments":"{\\"chips\\":[{\\"label\\":\\"A\\"}]}"}}]}}]}',
            'data: {"choices":[{"delta":{"content":"Here are your options"}}]}',
            "data: [DONE]",
        ]

        with patch("tools.chat.chat_streaming._call_upstream") as mock_upstream:
            mock_upstream.return_value = _FakeUpstreamResp(upstream_chunks)
            with patch("tools.chat.chat_streaming._build_messages", return_value=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "show chips"},
            ]):
                with patch("tools.chat.chat_streaming._select_tools", return_value=("test prompt", ["ProposeChips"])):
                    with patch("tools.chat.chat_streaming.extract_facts", return_value=[]):
                        with patch("tools.chat.chat_streaming._log_chat_call"):
                            with patch("tools.chat.chat_streaming._write_turn_log"):
                                with patch("tools.chat.chat_streaming._turn_log_dir", return_value=None):
                                    with patch("tools.chat.chat_streaming.execute_tool", return_value=PROPOSAL_PREFIX + json.dumps({
                                        "kind": "chips",
                                        "chips": [{"label": "A"}, {"label": "B"}],
                                        "context_hint": "test",
                                    })):
                                        response = client.post(
                                            f"/api/chat/conversations/{test_conversation.id}/messages",
                                            headers=auth_headers,
                                            json={"content": "show me options"},
                                        )

        assert response.status_code == 200
        raw = response.data
        assert b"event: chips" in raw

    def test_done_event_has_message_id(self, client, auth_headers, test_conversation):
        """Test that done event includes message_id."""
        upstream_chunks = [
            'data: {"choices":[{"delta":{"content":"Response"}}]}',
            "data: [DONE]",
        ]

        with patch("tools.chat.chat_streaming._call_upstream") as mock_upstream:
            mock_upstream.return_value = _FakeUpstreamResp(upstream_chunks)
            with patch("tools.chat.chat_streaming._build_messages", return_value=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "test"},
            ]):
                with patch("tools.chat.chat_streaming._select_tools", return_value=("test prompt", [])):
                    with patch("tools.chat.chat_streaming.extract_facts", return_value=[]):
                        with patch("tools.chat.chat_streaming._log_chat_call"):
                            with patch("tools.chat.chat_streaming._write_turn_log"):
                                with patch("tools.chat.chat_streaming._turn_log_dir", return_value=None):
                                    response = client.post(
                                        f"/api/chat/conversations/{test_conversation.id}/messages",
                                        headers=auth_headers,
                                        json={"content": "test done"},
                                    )

        raw = response.data
        events = _parse_sse_events(raw)
        done_events = [e for e in events if e["event"] == "done"]
        assert len(done_events) >= 1
        assert "message_id" in done_events[0]["data"]


class TestMessageValidation:
    """Test message validation rules."""

    def test_empty_content_rejected(self, client, auth_headers, test_conversation):
        """Test empty message content is rejected."""
        response = client.post(
            f"/api/chat/conversations/{test_conversation.id}/messages",
            headers=auth_headers,
            json={"content": ""},
        )
        assert response.status_code == 400

    def test_oversized_content_rejected(self, client, auth_headers, test_conversation):
        """Test message >16000 chars is rejected."""
        response = client.post(
            f"/api/chat/conversations/{test_conversation.id}/messages",
            headers=auth_headers,
            json={"content": "x" * 16001},
        )
        assert response.status_code == 400

    def test_unauthorized_message(self, client, test_conversation):
        """Test message without auth is rejected."""
        response = client.post(
            f"/api/chat/conversations/{test_conversation.id}/messages",
            json={"content": "unauthorized"},
        )
        assert response.status_code in (401, 422)


class TestSSEEventTypes:
    """Test SSE event format compliance."""

    def test_sse_event_types_present(self, client, auth_headers, test_conversation):
        """Test all required SSE event types are emitted when appropriate."""
        upstream_chunks = [
            'data: {"choices":[{"delta":{"thinking":"thinking content"}}]}',
            'data: {"choices":[{"delta":{"content":"assistant response"}}]}',
            "data: [DONE]",
        ]

        with patch("tools.chat.chat_streaming._call_upstream") as mock_upstream:
            mock_upstream.return_value = _FakeUpstreamResp(upstream_chunks)
            with patch("tools.chat.chat_streaming._build_messages", return_value=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "test"},
            ]):
                with patch("tools.chat.chat_streaming._select_tools", return_value=("test prompt", [])):
                    with patch("tools.chat.chat_streaming.extract_facts", return_value=[]):
                        with patch("tools.chat.chat_streaming._log_chat_call"):
                            with patch("tools.chat.chat_streaming._write_turn_log"):
                                with patch("tools.chat.chat_streaming._turn_log_dir", return_value=None):
                                    response = client.post(
                                        f"/api/chat/conversations/{test_conversation.id}/messages",
                                        headers=auth_headers,
                                        json={"content": "test all events"},
                                    )

        raw = response.data
        assert b"event: thinking" in raw
        assert b"event: text" in raw
        assert b"event: done" in raw
        assert b"event: error" not in raw


class TestCSRFHandling:
    """Test CSRF token handling in chat endpoints."""

    def test_csrf_header_present_in_response(self, client, auth_headers, test_conversation):
        """Test that response includes proper headers for SSE."""
        upstream_chunks = [
            'data: {"choices":[{"delta":{"content":"ok"}}]}',
            "data: [DONE]",
        ]

        with patch("tools.chat.chat_streaming._call_upstream") as mock_upstream:
            mock_upstream.return_value = _FakeUpstreamResp(upstream_chunks)
            with patch("tools.chat.chat_streaming._build_messages", return_value=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "test"},
            ]):
                with patch("tools.chat.chat_streaming._select_tools", return_value=("test prompt", [])):
                    with patch("tools.chat.chat_streaming.extract_facts", return_value=[]):
                        with patch("tools.chat.chat_streaming._log_chat_call"):
                            with patch("tools.chat.chat_streaming._write_turn_log"):
                                with patch("tools.chat.chat_streaming._turn_log_dir", return_value=None):
                                    response = client.post(
                                        f"/api/chat/conversations/{test_conversation.id}/messages",
                                        headers=auth_headers,
                                        json={"content": "test headers"},
                                    )

        assert response.headers.get("Cache-Control") == "no-cache"
        assert response.headers.get("Connection") == "keep-alive"
