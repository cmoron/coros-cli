from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Any

import httpx

# MCP protocol revision implemented by this minimal client.
MCP_PROTOCOL_VERSION = "2025-06-18"
_CLIENT_INFO = {"name": "coros-cli", "version": "0.1.0"}

# Token refresher: returns a fresh access token (and is expected to persist it).
Refresher = Callable[[], Awaitable[str]]


class McpClientError(Exception):
    """Raised when an MCP JSON-RPC call fails or the transport misbehaves."""


class McpAuthError(McpClientError):
    """Raised when the MCP server rejects the bearer token (HTTP 401)."""


def _parse_jsonrpc(resp: httpx.Response) -> dict[str, Any]:
    """Extract a single JSON-RPC message from a streamable-HTTP response.

    The MCP streamable-HTTP transport may answer a request with either a plain
    ``application/json`` body or a ``text/event-stream`` (SSE) body carrying the
    response as one or more ``data:`` events.
    """
    content_type = resp.headers.get("content-type", "")
    if "text/event-stream" not in content_type:
        return _as_dict(resp.json())

    message: dict[str, Any] | None = None
    for line in resp.text.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[len("data:") :].strip()
        if not payload:
            continue
        candidate = _as_dict(json.loads(payload))
        # A response carries result/error; keep the last such message.
        if "result" in candidate or "error" in candidate:
            message = candidate
    if message is None:
        raise McpClientError("MCP response: no JSON-RPC message in event stream")
    return message


def _as_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise McpClientError(f"MCP response: expected a JSON object, got {type(value).__name__}")
    return value


class McpClient:
    """Minimal MCP client over the streamable-HTTP transport.

    Supports ``initialize``, ``tools/list`` and ``tools/call``. On HTTP 401 it
    transparently refreshes the access token once (if a refresher is supplied)
    and retries the request.
    """

    def __init__(
        self,
        endpoint: str,
        access_token: str,
        *,
        refresher: Refresher | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._endpoint = endpoint
        self._token = access_token
        self._refresher = refresher
        self._http = httpx.AsyncClient(timeout=timeout)
        self._session_id: str | None = None
        self._next_id = 0
        self._initialized = False

    async def __aenter__(self) -> McpClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._http.aclose()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    async def _post(self, body: dict[str, Any]) -> httpx.Response:
        """POST a JSON-RPC body, refreshing the token once on a 401."""
        resp = await self._http.post(self._endpoint, json=body, headers=self._headers())
        if resp.status_code == 401 and self._refresher is not None:
            self._token = await self._refresher()
            resp = await self._http.post(self._endpoint, json=body, headers=self._headers())
        if resp.status_code == 401:
            raise McpAuthError("MCP server rejected the access token (401). Run `coros mcp auth`.")
        return resp

    async def _call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        resp = await self._post(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        if resp.status_code >= 400:
            raise McpClientError(f"MCP {method}: HTTP {resp.status_code} {resp.text[:200]}")

        session_id = resp.headers.get("mcp-session-id")
        if session_id:
            self._session_id = session_id

        message = _parse_jsonrpc(resp)
        if "error" in message:
            error = message["error"] or {}
            raise McpClientError(
                f"MCP {method}: [{error.get('code')}] {error.get('message', error)}"
            )
        return _as_dict(message.get("result", {}))

    async def _notify(self, method: str) -> None:
        resp = await self._post({"jsonrpc": "2.0", "method": method})
        if resp.status_code >= 400:
            raise McpClientError(f"MCP {method}: HTTP {resp.status_code} {resp.text[:200]}")

    async def initialize(self) -> dict[str, Any]:
        """Run the MCP handshake: ``initialize`` then the ``initialized`` notification."""
        result = await self._call(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": _CLIENT_INFO,
            },
        )
        await self._notify("notifications/initialized")
        self._initialized = True
        return result

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()

    async def list_tools(self) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        result = await self._call("tools/list", {})
        tools = result.get("tools", [])
        if not isinstance(tools, list):
            raise McpClientError("MCP tools/list: 'tools' is not a list")
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_initialized()
        return await self._call("tools/call", {"name": name, "arguments": arguments})
