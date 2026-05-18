from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx

from coros_cli.mcp.client import McpClient
from coros_cli.mcp.metadata import McpServerMetadata, metadata_for_region
from coros_cli.mcp.models import McpOAuthState, RegisteredClient
from coros_cli.mcp.oauth import (
    REDIRECT_URI,
    build_authorization_url,
    exchange_code,
    extract_authorization_code,
    refresh_access_token,
    register_client,
    revoke_token,
)
from coros_cli.mcp.pkce import code_challenge, generate_code_verifier, generate_state
from coros_cli.mcp.store import save_mcp_state
from coros_cli.models import Region


@dataclass(frozen=True, slots=True)
class PendingAuthorization:
    """In-progress authorization-code flow, awaiting the user's pasted redirect.

    Carries the PKCE ``code_verifier`` and ``state`` that must survive the round
    trip through the browser so the code can be exchanged and verified.
    """

    region: Region
    meta: McpServerMetadata
    client: RegisteredClient
    redirect_uri: str
    state: str
    code_verifier: str
    authorization_url: str


async def begin_authorization(region: Region) -> PendingAuthorization:
    """Register a client and build the authorization URL the user must open."""
    meta = metadata_for_region(region)
    async with httpx.AsyncClient(timeout=30) as http:
        client = await register_client(http, meta)
    verifier = generate_code_verifier()
    state = generate_state()
    url = build_authorization_url(
        meta, client, state=state, code_challenge=code_challenge(verifier)
    )
    return PendingAuthorization(
        region=region,
        meta=meta,
        client=client,
        redirect_uri=REDIRECT_URI,
        state=state,
        code_verifier=verifier,
        authorization_url=url,
    )


async def complete_authorization(pending: PendingAuthorization, pasted: str) -> McpOAuthState:
    """Validate the pasted redirect, exchange the code, and build OAuth state."""
    code = extract_authorization_code(pasted, pending.state)
    async with httpx.AsyncClient(timeout=30) as http:
        token = await exchange_code(
            http,
            pending.meta,
            pending.client,
            code=code,
            code_verifier=pending.code_verifier,
            redirect_uri=pending.redirect_uri,
        )
    return McpOAuthState.from_token(
        region=pending.region,
        issuer=pending.meta.issuer,
        client=pending.client,
        token=token,
    )


async def refresh_state(state: McpOAuthState) -> McpOAuthState:
    """Refresh the access token. Raises if no refresh token is stored."""
    if not state.refresh_token:
        raise RuntimeError("no refresh token stored; run `coros mcp auth` again")
    meta = _meta(state)
    async with httpx.AsyncClient(timeout=30) as http:
        token = await refresh_access_token(
            http, meta, state.registered_client(), state.refresh_token
        )
    return state.with_token(token)


async def ensure_fresh(state: McpOAuthState) -> McpOAuthState:
    """Return state with a non-expired access token, refreshing + saving if needed."""
    if not state.access_expired():
        return state
    refreshed = await refresh_state(state)
    save_mcp_state(refreshed)
    return refreshed


async def revoke(state: McpOAuthState) -> None:
    """Revoke the stored refresh token (best effort)."""
    token = state.refresh_token or state.access_token
    if not token:
        return
    meta = _meta(state)
    hint = "refresh_token" if state.refresh_token else "access_token"
    async with httpx.AsyncClient(timeout=30) as http:
        await revoke_token(http, meta, state.registered_client(), token, token_type_hint=hint)


def build_client(state: McpOAuthState, on_refresh: Callable[[McpOAuthState], None]) -> McpClient:
    """Build an MCP client that refreshes + persists its token on a 401.

    ``on_refresh`` is invoked with the updated state after a successful refresh
    so the caller can persist it and keep its own copy current.
    """
    meta = _meta(state)
    current = state

    async def refresher() -> str:
        nonlocal current
        current = await refresh_state(current)
        save_mcp_state(current)
        on_refresh(current)
        token = current.access_token
        if token is None:  # pragma: no cover - refresh always yields a token
            raise RuntimeError("token refresh returned no access token")
        return token

    token = state.access_token
    if token is None:
        raise RuntimeError("no access token stored; run `coros mcp auth`")
    return McpClient(meta.mcp_endpoint, token, refresher=refresher)


def _meta(state: McpOAuthState) -> McpServerMetadata:
    # region is a free-form str on the persisted model; metadata_for_region
    # falls back to EU for anything it does not recognise.
    return metadata_for_region(state.region)  # type: ignore[arg-type]
