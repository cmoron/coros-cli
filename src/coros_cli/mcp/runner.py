"""Shared plumbing to invoke a COROS MCP tool from a CLI command.

Centralises OAuth state loading, token refresh, and result rendering so each
top-level command stays a thin wrapper that just maps flags to tool arguments.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import typer
from rich.console import Console

from coros_cli.mcp.client import McpClientError
from coros_cli.mcp.models import McpOAuthState
from coros_cli.mcp.oauth import McpOAuthError
from coros_cli.mcp.session import build_client, ensure_fresh
from coros_cli.mcp.store import load_mcp_state, save_mcp_state

console = Console()
err_console = Console(stderr=True)


def default_timezone() -> str:
    """Best-effort IANA timezone of the host, falling back to UTC.

    Reads, in order: ``$TZ``, the ``/etc/localtime`` zoneinfo symlink target,
    and ``/etc/timezone``. The COROS MCP tools accept any IANA name.
    """
    tz = os.environ.get("TZ", "").lstrip(":")
    if tz:
        return tz
    try:
        link = os.readlink("/etc/localtime")
    except OSError:
        link = ""
    marker = "/zoneinfo/"
    if marker in link:
        return link.split(marker, 1)[1]
    try:
        with open("/etc/timezone", encoding="utf-8") as f:
            label = f.read().strip()
            if label:
                return label
    except OSError:
        pass
    return "UTC"


def load_state_or_exit() -> McpOAuthState:
    """Return the persisted OAuth state, or exit 1 with a hint to log in."""
    state = load_mcp_state()
    if state is None:
        err_console.print("[red]Not authenticated.[/red] Run: coros auth")
        raise typer.Exit(1)
    return state


async def _invoke(state: McpOAuthState, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    state = await ensure_fresh(state)
    client = build_client(state, save_mcp_state)
    async with client:
        return await client.call_tool(tool, args)


def call_tool(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Load OAuth state, refresh if needed, and invoke an MCP tool synchronously."""
    state = load_state_or_exit()
    try:
        return asyncio.run(_invoke(state, tool, arguments))
    except (McpClientError, McpOAuthError, RuntimeError) as e:
        err_console.print(f"[red]MCP error:[/red] {e}")
        raise typer.Exit(1) from e


def emit_json(payload: Any) -> None:
    """Dump a JSON payload to stdout, terminated by a newline."""
    sys.stdout.write(json.dumps(payload, indent=2, default=str))
    sys.stdout.write("\n")


def _unwrap_text(text: str) -> str:
    """COROS wraps its tool text in an extra JSON string layer — unwrap it.

    Tries to JSON-decode the text; if the result is itself a string, use it.
    Otherwise return the raw input. This keeps non-wrapped servers working.
    """
    try:
        decoded = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text
    return decoded if isinstance(decoded, str) else text


def render_result(result: dict[str, Any], *, json_output: bool) -> None:
    """Render an MCP tool result: text content blocks, or raw JSON on demand."""
    if json_output:
        emit_json(result)
        return
    if result.get("isError"):
        err_console.print("[red]Tool reported an error.[/red]")
    content = result.get("content")
    if not isinstance(content, list) or not content:
        emit_json(result)
        return
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            console.print(_unwrap_text(block.get("text", "")))
        else:
            emit_json(block)


def run(tool: str, arguments: dict[str, Any], *, json_output: bool) -> None:
    """End-to-end helper: call the tool then render its result."""
    render_result(call_tool(tool, arguments), json_output=json_output)
