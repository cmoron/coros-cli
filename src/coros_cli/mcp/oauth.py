from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from coros_cli.mcp.metadata import McpServerMetadata
from coros_cli.mcp.models import RegisteredClient, TokenResponse

CLIENT_NAME = "coros-cli"
AUTH_CODE_GRANT = "authorization_code"

# RFC 8252 §7.3 loopback redirect. coros-cli does NOT run a local HTTP server:
# after approval the browser will fail to load this URL ("connection refused"),
# which is expected. The user copies the address-bar URL back into the CLI.
REDIRECT_URI = "http://localhost:8765/callback"


class McpOAuthError(Exception):
    """Raised when an OAuth step fails (registration, authorization, token)."""


def _client_auth(client: RegisteredClient) -> dict[str, str]:
    """Token/revoke request params identifying the registered client.

    Registration is done as a public client (``token_endpoint_auth_method`` of
    ``none``), but COROS may still issue a secret — if so we send it via
    ``client_secret_post`` so either server policy works.
    """
    params = {"client_id": client.client_id}
    if client.client_secret:
        params["client_secret"] = client.client_secret
    return params


def _oauth_error(resp: httpx.Response, context: str) -> McpOAuthError:
    try:
        body = resp.json()
    except ValueError:
        body = {}
    code = body.get("error", resp.status_code)
    description = body.get("error_description") or resp.text[:200]
    return McpOAuthError(f"{context}: [{code}] {description}")


async def register_client(http: httpx.AsyncClient, meta: McpServerMetadata) -> RegisteredClient:
    """Perform OAuth 2.0 Dynamic Client Registration (RFC 7591).

    Registers a public client for the authorization-code grant. COROS normalises
    the registration regardless of what is requested: it returns the
    ``authorization_code``/``refresh_token`` grants and ``token_endpoint_auth_method``
    ``none``, which is exactly what this CLI relies on.
    """
    resp = await http.post(
        meta.registration_endpoint,
        json={
            "client_name": CLIENT_NAME,
            "grant_types": [AUTH_CODE_GRANT, "refresh_token"],
            "response_types": ["code"],
            "redirect_uris": [REDIRECT_URI],
            "token_endpoint_auth_method": "none",
            "scope": meta.scope_param,
        },
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    if resp.status_code not in (200, 201):
        raise _oauth_error(resp, "client registration")
    body = resp.json()
    client_id = body.get("client_id")
    if not client_id:
        raise McpOAuthError("client registration: no client_id in response")
    return RegisteredClient(client_id=client_id, client_secret=body.get("client_secret"))


def build_authorization_url(
    meta: McpServerMetadata,
    client: RegisteredClient,
    *,
    state: str,
    code_challenge: str,
    redirect_uri: str = REDIRECT_URI,
) -> str:
    """Build the browser URL for the authorization-code grant (RFC 6749 §4.1.1).

    ``code_challenge`` is the S256 PKCE challenge (RFC 7636).
    """
    params = {
        "response_type": "code",
        "client_id": client.client_id,
        "redirect_uri": redirect_uri,
        "scope": meta.scope_param,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{meta.authorization_endpoint}?{urlencode(params)}"


def extract_authorization_code(pasted: str, expected_state: str) -> str:
    """Pull the authorization ``code`` from what the user pasted back.

    Accepts either the full redirect URL from the browser address bar or a bare
    code. When a URL is pasted the ``state`` parameter is validated against
    ``expected_state`` to defend against CSRF; a bare code cannot be checked.
    """
    pasted = pasted.strip()
    if not pasted:
        raise McpOAuthError("authorization response: nothing was pasted")
    if "code=" not in pasted and "error=" not in pasted:
        # Treat the whole input as a bare authorization code.
        return pasted
    query = urlparse(pasted).query or pasted.lstrip("?")
    params = parse_qs(query)
    if "error" in params:
        description = params.get("error_description", [""])[0]
        raise McpOAuthError(f"authorization denied: {params['error'][0]} {description}".strip())
    codes = params.get("code", [])
    if not codes or not codes[0]:
        raise McpOAuthError("authorization response: no 'code' parameter in the pasted URL")
    state = params.get("state", [None])[0]
    if state != expected_state:
        raise McpOAuthError("authorization response: 'state' mismatch — possible CSRF, aborting")
    return codes[0]


async def _request_token(
    http: httpx.AsyncClient, meta: McpServerMetadata, data: dict[str, str]
) -> httpx.Response:
    return await http.post(
        meta.token_endpoint,
        data=data,
        headers={"Accept": "application/json"},
    )


async def exchange_code(
    http: httpx.AsyncClient,
    meta: McpServerMetadata,
    client: RegisteredClient,
    *,
    code: str,
    code_verifier: str,
    redirect_uri: str = REDIRECT_URI,
) -> TokenResponse:
    """Exchange an authorization code for tokens (RFC 6749 §4.1.3 + RFC 7636)."""
    resp = await _request_token(
        http,
        meta,
        {
            **_client_auth(client),
            "grant_type": AUTH_CODE_GRANT,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
    )
    if resp.status_code != 200:
        raise _oauth_error(resp, "authorization code exchange")
    return TokenResponse.model_validate(resp.json())


async def refresh_access_token(
    http: httpx.AsyncClient,
    meta: McpServerMetadata,
    client: RegisteredClient,
    refresh_token: str,
) -> TokenResponse:
    """Exchange a refresh token for a fresh access token (RFC 6749 §6)."""
    resp = await _request_token(
        http,
        meta,
        {
            **_client_auth(client),
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )
    if resp.status_code != 200:
        raise _oauth_error(resp, "token refresh")
    return TokenResponse.model_validate(resp.json())


async def revoke_token(
    http: httpx.AsyncClient,
    meta: McpServerMetadata,
    client: RegisteredClient,
    token: str,
    *,
    token_type_hint: str = "refresh_token",
) -> None:
    """Revoke a token (RFC 7009). A 200 with empty body is the success case."""
    resp = await http.post(
        meta.revocation_endpoint,
        data={**_client_auth(client), "token": token, "token_type_hint": token_type_hint},
        headers={"Accept": "application/json"},
    )
    if resp.status_code not in (200, 204):
        raise _oauth_error(resp, "token revocation")
