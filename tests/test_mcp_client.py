from __future__ import annotations

from typing import Any

import pytest
from pytest_httpx import HTTPXMock

from coros_cli.mcp.client import McpAuthError, McpClient, McpClientError

ENDPOINT = "https://mcpeu.coros.com/mcp"


def _result(payload: dict[str, Any], request_id: int = 1) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def _init_result() -> dict[str, Any]:
    return _result(
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "coros-mcp", "version": "1.0"},
        }
    )


def _add_handshake(httpx_mock: HTTPXMock, *, session_id: str | None = None) -> None:
    """Queue the initialize response + the 202 for the initialized notification."""
    headers = {"Mcp-Session-Id": session_id} if session_id else None
    httpx_mock.add_response(method="POST", url=ENDPOINT, json=_init_result(), headers=headers)
    httpx_mock.add_response(method="POST", url=ENDPOINT, status_code=202)


async def test_initialize_sends_bearer_token(httpx_mock: HTTPXMock) -> None:
    _add_handshake(httpx_mock)
    async with McpClient(ENDPOINT, "tok-abc") as client:
        result = await client.initialize()
    assert result["serverInfo"]["name"] == "coros-mcp"

    init_request = httpx_mock.get_requests()[0]
    assert init_request.headers["Authorization"] == "Bearer tok-abc"
    assert "application/json" in init_request.headers["Accept"]


async def test_list_tools_returns_tool_list(httpx_mock: HTTPXMock) -> None:
    _add_handshake(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=ENDPOINT,
        json=_result({"tools": [{"name": "get_sleep"}, {"name": "get_activities"}]}, 2),
    )
    async with McpClient(ENDPOINT, "tok") as client:
        tools = await client.list_tools()
    assert [t["name"] for t in tools] == ["get_sleep", "get_activities"]


async def test_call_tool_returns_result(httpx_mock: HTTPXMock) -> None:
    _add_handshake(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=ENDPOINT,
        json=_result({"content": [{"type": "text", "text": "ok"}], "isError": False}, 2),
    )
    async with McpClient(ENDPOINT, "tok") as client:
        result = await client.call_tool("get_sleep", {"days": 7})
    assert result["content"][0]["text"] == "ok"

    call_request = httpx_mock.get_requests()[-1]
    assert b'"tools/call"' in call_request.content
    assert b'"get_sleep"' in call_request.content


async def test_session_id_is_echoed_on_later_requests(httpx_mock: HTTPXMock) -> None:
    _add_handshake(httpx_mock, session_id="sess-99")
    httpx_mock.add_response(method="POST", url=ENDPOINT, json=_result({"tools": []}, 2))
    async with McpClient(ENDPOINT, "tok") as client:
        await client.list_tools()
    tools_request = httpx_mock.get_requests()[-1]
    assert tools_request.headers["Mcp-Session-Id"] == "sess-99"


async def test_refreshes_token_on_401_and_retries(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=ENDPOINT, status_code=401)
    _add_handshake(httpx_mock)
    httpx_mock.add_response(method="POST", url=ENDPOINT, json=_result({"tools": []}, 2))

    refreshed = False

    async def refresher() -> str:
        nonlocal refreshed
        refreshed = True
        return "new-token"

    async with McpClient(ENDPOINT, "stale-token", refresher=refresher) as client:
        await client.list_tools()

    assert refreshed is True
    requests = httpx_mock.get_requests()
    assert requests[0].headers["Authorization"] == "Bearer stale-token"
    assert requests[1].headers["Authorization"] == "Bearer new-token"


async def test_raises_mcp_auth_error_without_refresher(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=ENDPOINT, status_code=401)
    async with McpClient(ENDPOINT, "stale") as client:
        with pytest.raises(McpAuthError):
            await client.initialize()


async def test_parses_sse_response(httpx_mock: HTTPXMock) -> None:
    import json as _json

    sse_body = f"event: message\ndata: {_json.dumps(_init_result())}\n\n"
    httpx_mock.add_response(
        method="POST",
        url=ENDPOINT,
        text=sse_body,
        headers={"content-type": "text/event-stream"},
    )
    httpx_mock.add_response(method="POST", url=ENDPOINT, status_code=202)
    async with McpClient(ENDPOINT, "tok") as client:
        result = await client.initialize()
    assert result["serverInfo"]["name"] == "coros-mcp"


async def test_raises_on_jsonrpc_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=ENDPOINT,
        json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "no such method"}},
    )
    async with McpClient(ENDPOINT, "tok") as client:
        with pytest.raises(McpClientError, match="no such method"):
            await client.initialize()
