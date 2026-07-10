"""MCP Client untuk komunikasi dengan MCP Playwright Server.

Implements MCP stdio transport protocol:
- Content-Length header framing (Content-Length: N\\r\\n\\r\\n<JSON>)
- Initialize handshake
- JSON-RPC 2.0 request/response
- Concurrent stderr reader (prevents pipe buffer deadlock)

Usage:
    from tools.Literatur.fetchers.mcp_client import PlaywrightMCPClient

    async with PlaywrightMCPClient() as client:
        await client.initialize()
        result = await client.fetch_page("https://www.researchgate.net")
        html = result["html"]
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Path ke MCP server script
MCP_SERVER_PATH = Path(__file__).parent.parent.parent.parent / "mcp_servers" / "playwright" / "server.js"


class PlaywrightMCPClient:
    """Client untuk MCP Playwright Server via stdio transport.

    Implements MCP protocol with Content-Length framing and initialize handshake.
    """

    def __init__(self, server_path: str | Path | None = None):
        self.server_path = Path(server_path) if server_path else MCP_SERVER_PATH
        self.process = None
        self.reader = None
        self.writer = None
        self._stderr_task = None
        self._request_id = 0
        self._initialized = False

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def __aenter__(self):
        """Start MCP server process and establish stdio connection."""
        if not self.server_path.exists():
            raise FileNotFoundError(
                f"MCP server not found: {self.server_path}\n"
                f"Run: cd {self.server_path.parent} && npm install"
            )

        self.process = await asyncio.create_subprocess_exec(
            "node",
            str(self.server_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=10_485_760,  # 10MB buffer — large HTML responses
        )

        self.reader = self.process.stdout
        self.writer = self.process.stdin

        # Start stderr reader to prevent pipe buffer deadlock
        self._stderr_task = asyncio.create_task(self._drain_stderr())

        log.info("MCP Playwright client connected (PID: %s)", self.process.pid)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Terminate MCP server process cleanly."""
        # Cancel stderr reader
        if self._stderr_task:
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass

        # Close stdin
        if self.writer:
            try:
                self.writer.close()
                # Don't wait_closed() — avoids hang if server doesn't close its stdin
            except Exception:
                pass

        # Terminate process
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
            except Exception:
                pass

        log.info("MCP Playwright client disconnected")

    async def _drain_stderr(self):
        """Read stderr in background to prevent pipe buffer deadlock."""
        try:
            while True:
                line = await self.process.stderr.readline()
                if not line:
                    break
                # Log stderr messages for debugging
                stderr_line = line.decode("utf-8", errors="replace").rstrip()
                if stderr_line:
                    log.debug("[MCP server stderr] %s", stderr_line)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.debug("Stderr reader ended: %s", e)

    # ── MCP Protocol ────────────────────────────────────────────────────────

    async def initialize(self):
        """Send MCP initialize request (required before any other call)."""
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "papergenerator-mcp-client",
                "version": "1.0.0",
            },
        })
        self._initialized = True
        log.info("MCP initialized: server=%s v%s",
                 result.get("serverInfo", {}).get("name", "unknown"),
                 result.get("serverInfo", {}).get("version", "?"))
        return result

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send JSON-RPC request via MCP stdio transport (newline-delimited JSON).

        MCP SDK StdioServerTransport uses newline-delimited JSON, not
        Content-Length framing. Each line is a complete JSON-RPC message.
        """
        request_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        request_json = json.dumps(request, ensure_ascii=False)

        self.writer.write((request_json + "\n").encode("utf-8"))
        await self.writer.drain()

        # Read response (newline-delimited JSON)
        response = await self._read_response(request_id)

        if "error" in response:
            err = response["error"]
            raise RuntimeError(
                f"MCP error {err.get('code', -1)}: {err.get('message', 'unknown')}"
            )

        return response.get("result", {})

    async def _read_response(self, expected_id: int) -> dict[str, Any]:
        """Read newline-delimited JSON-RPC response from stdout.

        MCP responses (especially fetch_page) contain large HTML bodies inside
        the JSON payload. Set limit=10MB to avoid BufferOverrunError on large pages.
        """
        # 10MB buffer set at subprocess creation — enough for full HTML pages
        line = await self.reader.readline()
        if not line:
            raise ConnectionError("MCP server closed connection unexpectedly")

        try:
            body = json.loads(line.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Invalid JSON from MCP server: {line.decode('utf-8', errors='replace')[:200]}"
            ) from e

        # Validate response ID
        response_id = body.get("id")
        if response_id is not None and response_id != expected_id:
            log.warning(
                "MCP response ID mismatch: expected %d, got %s", expected_id, response_id
            )

        return body

    # ── Public API ──────────────────────────────────────────────────────────

    async def list_tools(self) -> list[dict]:
        """List available tools dari MCP server."""
        if not self._initialized:
            await self.initialize()
        result = await self._send_request("tools/list", {})
        return result.get("tools", [])

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call tool via MCP server.

        Returns:
            Tool result sebagai dict (parsed from JSON text content).
        """
        if not self._initialized:
            await self.initialize()

        result = await self._send_request(
            "tools/call",
            {"name": tool_name, "arguments": arguments}
        )

        content = result.get("content", [])
        if not content:
            return {}

        first_content = content[0]
        content_type = first_content.get("type", "text")

        if content_type == "text":
            return json.loads(first_content.get("text", "{}"))
        elif content_type == "image":
            log.warning("Tool '%s' returned image content (not supported yet)", tool_name)
            return {"_image": first_content}
        elif content_type == "resource":
            log.warning("Tool '%s' returned resource content", tool_name)
            return {"_resource": first_content}
        else:
            log.warning("Tool '%s' returned unknown content type: %s", tool_name, content_type)
            return {"_unknown": first_content}

    async def fetch_page(
        self,
        url: str,
        wait_selector: str | None = None,
        timeout: int = 30
    ) -> dict[str, Any]:
        """Fetch single page HTML.

        Returns:
            {"success": bool, "html": str, "url": str, "title": str, "status": int}
        """
        args = {"url": url, "timeout": timeout}
        if wait_selector:
            args["wait_selector"] = wait_selector

        return await self.call_tool("fetch_page", args)

    async def fetch_pages(
        self,
        urls: list[str],
        delay_min: int = 2000,
        delay_max: int = 5000
    ) -> dict[str, Any]:
        """Fetch multiple pages in batch.

        Returns:
            {"success": bool, "results": [{"url": str, "success": bool, "html": str, "title": str}, ...]}
        """
        return await self.call_tool("fetch_pages", {
            "urls": urls,
            "delay_min": delay_min,
            "delay_max": delay_max,
        })


# ══════════════════════════════════════════════════════════════════════════════
# Sync wrappers — safe for both sync and async contexts
# ══════════════════════════════════════════════════════════════════════════════

def _run_async(coro):
    """Run async function safely — works in both sync and async contexts."""
    try:
        loop = asyncio.get_running_loop()
        # Already in async context — use ThreadPoolExecutor to avoid nested loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=60)
    except RuntimeError:
        # No running event loop — safe to use asyncio.run()
        return asyncio.run(coro)


def fetch_page_sync(url: str, wait_selector: str | None = None, timeout: int = 30) -> dict[str, Any]:
    """Synchronous wrapper for fetch_page (safe for any context)."""
    async def _run():
        async with PlaywrightMCPClient() as client:
            return await client.fetch_page(url, wait_selector, timeout)

    return _run_async(_run())


def fetch_pages_sync(urls: list[str], delay_min: int = 2000, delay_max: int = 5000) -> dict[str, Any]:
    """Synchronous wrapper for fetch_pages (safe for any context)."""
    async def _run():
        async with PlaywrightMCPClient() as client:
            return await client.fetch_pages(urls, delay_min, delay_max)

    return _run_async(_run())