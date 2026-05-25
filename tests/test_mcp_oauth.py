from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from pytest_httpx import HTTPXMock

from coros_cli.mcp.metadata import metadata_for_region
from coros_cli.mcp.models import RegisteredClient
from coros_cli.mcp.oauth import (
    REDIRECT_URI,
    McpOAuthError,
    build_authorization_url,
    exchange_code,
    extract_authorization_code,
    refresh_access_token,
    register_client,
    revoke_token,
)

META = metadata_for_region("eu")
CLIENT = RegisteredClient(client_id="cli-1", client_secret=None)


# --- dynamic registration ---------------------------------------------------


async def test_register_client_sends_authorization_code_payload(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=META.registration_endpoint,
        status_code=201,
        json={"client_id": "abc-123", "client_secret": "sek"},
    )
    async with httpx.AsyncClient() as http:
        client = await register_client(http, META)
    assert client.client_id == "abc-123"
    assert client.client_secret == "sek"

    request = httpx_mock.get_request()
    assert request is not None
    payload = json.loads(request.content)
    assert payload["grant_types"] == ["authorization_code", "refresh_token"]
    assert payload["response_types"] == ["code"]
    assert payload["redirect_uris"] == [REDIRECT_URI]
    assert payload["token_endpoint_auth_method"] == "none"
    assert payload["scope"] == "openid mcp.tools offline_access"


async def test_register_client_raises_on_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=META.registration_endpoint,
        status_code=400,
        json={"error": "invalid_client_metadata"},
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(McpOAuthError, match="invalid_client"):
            await register_client(http, META)


# --- authorization URL ------------------------------------------------------


def test_build_authorization_url_carries_pkce_and_state() -> None:
    url = build_authorization_url(META, CLIENT, state="st-123", code_challenge="chal-xyz")
    parsed = urlparse(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == META.authorization_endpoint
    params = parse_qs(parsed.query)
    assert params["response_type"] == ["code"]
    assert params["client_id"] == ["cli-1"]
    assert params["redirect_uri"] == [REDIRECT_URI]
    assert params["scope"] == ["openid mcp.tools offline_access"]
    assert params["state"] == ["st-123"]
    assert params["code_challenge"] == ["chal-xyz"]
    assert params["code_challenge_method"] == ["S256"]


# --- code extraction / state validation -------------------------------------


def test_extract_code_from_full_redirect_url() -> None:
    url = f"{REDIRECT_URI}?code=the-code&state=expected"
    assert extract_authorization_code(url, "expected") == "the-code"


def test_extract_code_accepts_bare_code() -> None:
    assert extract_authorization_code("just-a-code", "expected") == "just-a-code"


def test_extract_code_rejects_state_mismatch() -> None:
    url = f"{REDIRECT_URI}?code=the-code&state=tampered"
    with pytest.raises(McpOAuthError, match="state"):
        extract_authorization_code(url, "expected")


def test_extract_code_surfaces_error_in_url() -> None:
    url = f"{REDIRECT_URI}?error=access_denied&error_description=user+said+no"
    with pytest.raises(McpOAuthError, match="access_denied"):
        extract_authorization_code(url, "expected")


def test_extract_code_rejects_empty_input() -> None:
    with pytest.raises(McpOAuthError, match="nothing"):
        extract_authorization_code("   ", "expected")


# --- token exchange ---------------------------------------------------------


async def test_exchange_code_returns_token(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=META.token_endpoint,
        json={
            "access_token": "acc-tok",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "ref-tok",
            "scope": "openid mcp.tools offline_access",
        },
    )
    async with httpx.AsyncClient() as http:
        token = await exchange_code(http, META, CLIENT, code="auth-code", code_verifier="verif-1")
    assert token.access_token == "acc-tok"
    assert token.refresh_token == "ref-tok"

    request = httpx_mock.get_request()
    assert request is not None
    sent = parse_qs(request.content.decode())
    assert sent["grant_type"] == ["authorization_code"]
    assert sent["code"] == ["auth-code"]
    assert sent["code_verifier"] == ["verif-1"]
    assert sent["redirect_uri"] == [REDIRECT_URI]
    assert sent["client_id"] == ["cli-1"]


async def test_exchange_code_raises_on_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=META.token_endpoint,
        status_code=400,
        json={"error": "invalid_grant"},
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(McpOAuthError, match="invalid_grant"):
            await exchange_code(http, META, CLIENT, code="bad", code_verifier="v")


# --- refresh / revoke -------------------------------------------------------


async def test_refresh_access_token_returns_new_token(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=META.token_endpoint,
        json={"access_token": "fresh", "token_type": "Bearer", "expires_in": 3600},
    )
    async with httpx.AsyncClient() as http:
        token = await refresh_access_token(http, META, CLIENT, "old-refresh")
    assert token.access_token == "fresh"

    request = httpx_mock.get_requests()[0]
    assert b"grant_type=refresh_token" in request.content
    assert b"refresh_token=old-refresh" in request.content


async def test_refresh_access_token_raises_on_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=META.token_endpoint,
        status_code=400,
        json={"error": "invalid_grant"},
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(McpOAuthError, match="invalid_grant"):
            await refresh_access_token(http, META, CLIENT, "old-refresh")


async def test_revoke_token_succeeds_on_200(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=META.revocation_endpoint, status_code=200)
    async with httpx.AsyncClient() as http:
        await revoke_token(http, META, CLIENT, "ref-tok")
    request = httpx_mock.get_requests()[0]
    assert b"token=ref-tok" in request.content
