from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from pytest_httpx import HTTPXMock

from coros_cli.mcp.metadata import metadata_for_region
from coros_cli.mcp.oauth import McpOAuthError
from coros_cli.mcp.session import begin_authorization, complete_authorization

META = metadata_for_region("eu")


async def test_begin_authorization_registers_and_builds_url(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=META.registration_endpoint,
        status_code=201,
        json={"client_id": "reg-client"},
    )
    pending = await begin_authorization("eu")
    assert pending.client.client_id == "reg-client"
    assert pending.code_verifier and pending.state
    params = parse_qs(urlparse(pending.authorization_url).query)
    assert params["client_id"] == ["reg-client"]
    assert params["state"] == [pending.state]
    # The challenge in the URL must derive from the stored verifier.
    assert params["code_challenge_method"] == ["S256"]


async def test_complete_authorization_exchanges_code(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=META.registration_endpoint,
        status_code=201,
        json={"client_id": "reg-client"},
    )
    httpx_mock.add_response(
        method="POST",
        url=META.token_endpoint,
        json={
            "access_token": "acc",
            "refresh_token": "ref",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )
    pending = await begin_authorization("eu")
    redirect = f"{pending.redirect_uri}?code=the-code&state={pending.state}"
    state = await complete_authorization(pending, redirect)
    assert state.access_token == "acc"
    assert state.refresh_token == "ref"
    assert state.region == "eu"
    assert state.client_id == "reg-client"


async def test_complete_authorization_rejects_bad_state(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=META.registration_endpoint,
        status_code=201,
        json={"client_id": "reg-client"},
    )
    pending = await begin_authorization("eu")
    redirect = f"{pending.redirect_uri}?code=the-code&state=wrong"
    with pytest.raises(McpOAuthError, match="state"):
        await complete_authorization(pending, redirect)
