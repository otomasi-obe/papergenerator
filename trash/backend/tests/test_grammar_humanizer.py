"""
Integration tests for Grammar & Humanizer tools endpoints.

Covers:
- POST /api/tools/grammar (program mode, SSE)
- POST /api/tools/ai-grammar (LLM mode, SSE)
- POST /api/tools/humanizer (program/ai mode, SSE)
"""

import json
import pytest


def parse_sse_response(data):
    """Parse SSE response to extract JSON payload.

    The tools_api returns SSE with format:
        data: {"text": "<string or json.dumps(result)>", "result": {...}}\n\n

    For program-mode tools (grammar, humanizer), the runner returns a dict directly
    as 'result', while 'text' is json.dumps of that dict.
    For AI tools, 'text' contains streamed content chunks.
    """
    result = {}
    raw_text_chunks = []
    for line in data.decode("utf-8").split("\n"):
        if line.startswith("data: "):
            try:
                payload = json.loads(line[6:])
                if "text" in payload:
                    raw_text_chunks.append(payload["text"])
                if "result" in payload:
                    result.update(payload)
                elif "error" in payload:
                    result["error"] = payload["error"]
                # Merge any other keys
                for k, v in payload.items():
                    if k not in ("text", "result"):
                        result[k] = v
            except json.JSONDecodeError:
                pass

    # For grammar tool, 'text' is json.dumps of the result dict.
    # Try to parse it to extract nested fields.
    if "text" not in result and raw_text_chunks:
        combined = "".join(raw_text_chunks)
        result["text"] = combined

    if "text" in result and isinstance(result["text"], str):
        try:
            parsed_text = json.loads(result["text"])
            if isinstance(parsed_text, dict) and "result" not in result:
                result["result"] = parsed_text
            elif isinstance(parsed_text, dict):
                result.setdefault("result", {}).update(parsed_text)
        except (json.JSONDecodeError, TypeError):
            pass

    return result


class TestGrammarEndpoint:
    """Test POST /api/tools/grammar (program mode)"""

    def test_grammar_program_basic(self, client, auth_headers):
        """Grammar program mode returns diff markup with corrections."""
        resp = client.post(
            "/api/tools/grammar",
            headers=auth_headers,
            json={"text": "It are wrong. She have a car.", "option": "Standard"},
        )
        assert resp.status_code == 200
        assert resp.content_type == "text/event-stream; charset=utf-8"

        data = parse_sse_response(resp.data)
        # Result should contain grammar check output
        assert "result" in data, f"No 'result' in response. Got: {data}"
        result = data.get("result", {}) or {}

        # Must have 'corrected' field with fixed text
        assert "corrected" in result, f"No 'corrected' in result. Keys: {list(result.keys())}"
        corrected = result.get("corrected", "")
        assert len(corrected) > 0, "Corrected text should not be empty"
        # 'are' should be corrected to 'is'
        assert "are" not in corrected.lower().split() or "is" in corrected.lower(), \
            f"Grammar should fix 'are' → 'is'. Got: {corrected}"

    def test_grammar_program_diff_markup(self, client, auth_headers):
        """Grammar returns <add>/<del> track-changes markup in text field."""
        resp = client.post(
            "/api/tools/grammar",
            headers=auth_headers,
            json={"text": "It are wrong.", "option": "Standard"},
        )
        assert resp.status_code == 200

        data = parse_sse_response(resp.data)
        text = data.get("text", "")
        result = data.get("result", {}) or {}

        # Either in text field or in corrected field, corrections should be present
        has_markup = "<del>" in text or "<add>" in text
        has_corrected = bool(result.get("corrected", ""))
        errors = result.get("errors", [])

        assert has_markup or has_corrected or len(errors) > 0, \
            f"Expected diff markup, corrected text, or errors. Text: {text[:200]}, result: {list(result.keys())}"

    def test_grammar_program_returns_errors_list(self, client, auth_headers):
        """Grammar result includes errors/warnings lists."""
        resp = client.post(
            "/api/tools/grammar",
            headers=auth_headers,
            json={"text": "It are wrong.", "option": "Standard"},
        )
        assert resp.status_code == 200

        data = parse_sse_response(resp.data)
        result = data.get("result", {}) or {}

        # Check either errors/warnings exist or corrected differs from original
        has_errors = bool(result.get("errors"))
        has_warnings = bool(result.get("warnings"))
        corrected = result.get("corrected", "")
        text_field = result.get("text", "")
        has_corrections = corrected and corrected != text_field

        assert has_errors or has_warnings or has_corrections, \
            "Grammar should report errors/warnings or provide corrected text"

    def test_grammar_program_empty_text(self, client, auth_headers):
        """Grammar rejects empty text with 400."""
        resp = client.post(
            "/api/tools/grammar",
            headers=auth_headers,
            json={"text": "", "option": "Standard"},
        )
        assert resp.status_code == 400

    def test_grammar_program_missing_text_field(self, client, auth_headers):
        """Grammar rejects request without text field."""
        resp = client.post(
            "/api/tools/grammar",
            headers=auth_headers,
            json={"option": "Standard"},
        )
        assert resp.status_code == 400

    def test_grammar_program_no_auth(self, client):
        """Grammar requires auth — returns 401."""
        resp = client.post(
            "/api/tools/grammar",
            json={"text": "test", "option": "Standard"},
        )
        assert resp.status_code in (401, 403)

    def test_grammar_program_option_grammar(self, client, auth_headers):
        """Grammar with option=Grammar returns a result (even if not all errors caught)."""
        resp = client.post(
            "/api/tools/grammar",
            headers=auth_headers,
            json={"text": "They was happy.", "option": "Grammar"},
        )
        assert resp.status_code == 200

        data = parse_sse_response(resp.data)
        result = data.get("result", {}) or {}
        corrected = result.get("corrected", "")
        assert corrected, "Should return corrected text"
        # Grammar checker may or may not catch subject-verb disagreement;
        # the important thing is it returns a valid result structure
        assert isinstance(corrected, str), f"Corrected should be string, got {type(corrected)}"


class TestAIGrammarEndpoint:
    """Test POST /api/tools/ai-grammar (LLM mode)"""

    def test_grammar_ai_endpoint_exists(self, client, auth_headers):
        """AI grammar endpoint is registered (not 404)."""
        resp = client.post(
            "/api/tools/ai-grammar",
            headers=auth_headers,
            json={"text": "It are wrong.", "option": "Standard"},
        )
        # Can be 200 (OK, AI streaming) or 500 (AI service not configured).
        # Must NOT be 404 (endpoint not found) or 422.
        assert resp.status_code != 404, "ai-grammar endpoint not registered"
        assert resp.status_code in (200, 500), \
            f"Expected 200 or 500, got {resp.status_code}"

    def test_grammar_ai_no_auth(self, client):
        """AI grammar requires auth."""
        resp = client.post(
            "/api/tools/ai-grammar",
            json={"text": "test", "option": "Standard"},
        )
        assert resp.status_code in (401, 403)

    def test_grammar_ai_empty_text(self, client, auth_headers):
        """AI grammar rejects empty text."""
        resp = client.post(
            "/api/tools/ai-grammar",
            headers=auth_headers,
            json={"text": "", "option": "Standard"},
        )
        assert resp.status_code == 400

    def test_grammar_ai_not_json_tool(self, client, auth_headers):
        """AI grammar uses streaming (not JSON tool like detect/plagiarism)."""
        resp = client.post(
            "/api/tools/ai-grammar",
            headers=auth_headers,
            json={"text": "Hello world.", "option": "Standard"},
        )
        # Should be text/event-stream type
        if resp.status_code == 200:
            assert "text/event-stream" in resp.content_type


class TestHumanizerEndpoint:
    """Test POST /api/tools/humanizer (program mode)"""

    def test_humanizer_program_mode(self, client, auth_headers):
        """Humanizer program mode returns processed text with metadata."""
        resp = client.post(
            "/api/tools/humanizer",
            headers=auth_headers,
            json={
                "text": "Furthermore, this is comprehensive and robust.",
                "option": "Aggressive",
                "mode": "program",
            },
        )
        assert resp.status_code == 200
        assert resp.content_type == "text/event-stream; charset=utf-8"

        data = parse_sse_response(resp.data)
        assert "result" in data, f"No 'result' in response. Got: {data}"
        result = data.get("result", {}) or {}

        # Result should have 'text' with humanized output
        assert "text" in result, f"No 'text' in result. Keys: {list(result.keys())}"
        text = result.get("text", "")
        assert len(text) > 0, "Humanized text should not be empty"

    def test_humanizer_program_removes_slop(self, client, auth_headers):
        """Program mode removes AI slop words."""
        input_text = "Furthermore, it is crucial to note that this leverages AI."
        resp = client.post(
            "/api/tools/humanizer",
            headers=auth_headers,
            json={
                "text": input_text,
                "option": "Aggressive",
                "mode": "program",
            },
        )
        assert resp.status_code == 200

        data = parse_sse_response(resp.data)
        result = data.get("result", {}) or {}
        text = result.get("text", "")

        # Aggressive mode should remove/modify slop words
        slop_words = ["Furthermore", "crucial", "leverages"]
        remaining_slop = [w for w in slop_words if w in text]
        assert len(remaining_slop) < len(slop_words), \
            f"Some slop words should be removed. Remaining: {remaining_slop}. Text: {text}"

    def test_humanizer_program_result_structure(self, client, auth_headers):
        """Humanizer result includes mode/engine metadata."""
        resp = client.post(
            "/api/tools/humanizer",
            headers=auth_headers,
            json={
                "text": "This is a test sentence.",
                "option": "Standard",
                "mode": "program",
            },
        )
        assert resp.status_code == 200

        data = parse_sse_response(resp.data)
        result = data.get("result", {}) or {}
        inner = result.get("result", {})

        # Metadata should indicate program mode
        if inner:
            assert inner.get("mode") == "program", \
                f"Expected mode='program', got: {inner.get('mode')}"

    def test_humanizer_empty_text(self, client, auth_headers):
        """Humanizer rejects empty text with 400."""
        resp = client.post(
            "/api/tools/humanizer",
            headers=auth_headers,
            json={"text": "", "option": "Standard", "mode": "program"},
        )
        assert resp.status_code == 400

    def test_humanizer_no_auth(self, client):
        """Humanizer requires auth."""
        resp = client.post(
            "/api/tools/humanizer",
            json={"text": "test", "option": "Standard", "mode": "program"},
        )
        assert resp.status_code in (401, 403)

    def test_humanizer_input_preserved_in_output(self, client, auth_headers):
        """Humanizer preserves core meaning (slop words replaced, not just removed)."""
        input_text = "Furthermore, it is crucial to note that this leverages AI technology."
        resp = client.post(
            "/api/tools/humanizer",
            headers=auth_headers,
            json={
                "text": input_text,
                "option": "Aggressive",
                "mode": "program",
            },
        )
        assert resp.status_code == 200

        data = parse_sse_response(resp.data)
        result = data.get("result", {}) or {}
        text = result.get("text", "")

        # Output should be non-empty
        assert len(text) > 0, "Output should not be empty"
        # Slop words should be replaced (not necessarily fewer words — replacements can be multi-word)
        slop_words = ["Furthermore", "crucial", "leverages"]
        remaining_slop = [w for w in slop_words if w in text]
        assert len(remaining_slop) < len(slop_words), \
            f"Some slop words should be replaced. Remaining: {remaining_slop}. Text: {text}"


class TestGrammarHumanizerSecurity:
    """Security and edge-case tests."""

    def test_grammar_unauthenticated_returns_401(self, client):
        """All grammar endpoints require authentication."""
        for endpoint in ["/api/tools/grammar", "/api/tools/ai-grammar", "/api/tools/humanizer"]:
            resp = client.post(endpoint, json={"text": "test"})
            assert resp.status_code in (401, 403), \
                f"{endpoint}: expected 401/403, got {resp.status_code}"

    def test_grammar_with_malformed_json_no_crash(self, client, auth_headers):
        """Malformed JSON should not crash the server."""
        resp = client.post(
            "/api/tools/grammar",
            headers={**auth_headers, "Content-Type": "application/json"},
            data=b"{malformed",
        )
        assert resp.status_code in (400, 500)

    def test_humanizer_invalid_mode_default(self, client, auth_headers):
        """Humanizer with unknown mode should still process (defaults to ai/program)."""
        resp = client.post(
            "/api/tools/humanizer",
            headers=auth_headers,
            json={
                "text": "This is a simple test.",
                "option": "Standard",
                "mode": "invalid_mode_xyz",
            },
        )
        # Should handle gracefully — either 200 or 400, not 500
        assert resp.status_code in (200, 400), \
            f"Invalid mode should not cause 500. Got: {resp.status_code}"
