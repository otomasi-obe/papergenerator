"""MCP Client untuk komunikasi dengan MCP Playwright Server.

AI Agent → MCP Client (Python) → MCP Server (Node.js) → Playwright → Website

Usage:
    from tools.Literatur.fetchers.mcp_client import PlaywrightMCPClient

    async with PlaywrightMCPClient() as client:
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
    """Client untuk MCP Playwright Server via stdio transport."""

    def __init__(self, server_path: str | Path | None = None):
        """
        Args:
            server_path: Path ke server.js. Default: auto-detect dari struktur proyek.
        """
        self.server_path = Path(server_path) if server_path else MCP_SERVER_PATH
        self.process = None
        self.reader = None
        self.writer = None

    async def __aenter__(self):
        """Start MCP server process dan establish stdio connection."""
        if not self.server_path.exists():
            raise FileNotFoundError(
                f"MCP server not found: {self.server_path}\n"
                f"Run: cd {self.server_path.parent} && npm install"
            )

        # Launch MCP server via Node.js
        self.process = await asyncio.create_subprocess_exec(
            "node",
            str(self.server_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        self.reader = self.process.stdout
        self.writer = self.process.stdin

        log.info("MCP Playwright client connected (PID: %s)", self.process.pid)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Terminate MCP server process."""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        
        log.info("MCP Playwright client disconnected")

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send JSON-RPC request ke MCP server via stdio."""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
        
        request_json = json.dumps(request) + "\n"
        self.writer.write(request_json.encode())
        await self.writer.drain()

        # Read response
        response_line = await self.reader.readline()
        response = json.loads(response_line.decode())

        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")
        
        return response.get("result", {})

    async def list_tools(self) -> list[dict]:
        """List available tools dari MCP server."""
        result = await self._send_request("tools/list", {})
        return result.get("tools", [])

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call tool via MCP server.
        
        Args:
            tool_name: Tool name (fetch_page, fetch_pages)
            arguments: Tool arguments
            
        Returns:
            Tool result sebagai dict
        """
        result = await self._send_request(
            "tools/call",
            {"name": tool_name, "arguments": arguments}
        )
        
        # Extract text content dari MCP response
        content = result.get("content", [])
        if content and content[0].get("type") == "text":
            return json.loads(content[0]["text"])
        
        return {}

    async def fetch_page(
        self,
        url: str,
        wait_selector: str | None = None,
        timeout: int = 30
    ) -> dict[str, Any]:
        """Fetch single page HTML.
        
        Args:
            url: URL to fetch
            wait_selector: CSS selector to wait for
            timeout: Max wait time in seconds
            
        Returns:
            {
                "success": bool,
                "html": str,
                "url": str,
                "title": str,
                "status": int
            }
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
        
        Args:
            urls: List of URLs
            delay_min: Min delay between requests (ms)
            delay_max: Max delay between requests (ms)
            
        Returns:
            {
                "success": bool,
                "results": [
                    {"url": str, "success": bool, "html": str, "title": str},
                    ...
                ]
            }
        """
        return await self.call_tool("fetch_pages", {
            "urls": urls,
            "delay_min": delay_min,
            "delay_max": delay_max,
        })


# ══════════════════════════════════════════════════════════════════════════════
# Sync wrappers untuk backward compatibility
# ══════════════════════════════════════════════════════════════════════════════

def fetch_page_sync(url: str, wait_selector: str | None = None, timeout: int = 30) -> dict[str, Any]:
    """Synchronous wrapper untuk fetch_page."""
    async def _run():
        async with PlaywrightMCPClient() as client:
            return await client.fetch_page(url, wait_selector, timeout)
    
    return asyncio.run(_run())


def fetch_pages_sync(urls: list[str], delay_min: int = 2000, delay_max: int = 5000) -> dict[str, Any]:
    """Synchronous wrapper untuk fetch_pages."""
    async def _run():
        async with PlaywrightMCPClient() as client:
            return await client.fetch_pages(urls, delay_min, delay_max)
    
    return asyncio.run(_run())
