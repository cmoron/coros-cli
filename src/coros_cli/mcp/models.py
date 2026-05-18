from __future__ import annotations

import time

from pydantic import BaseModel, Field

# Access tokens are considered expired this far before their real deadline, so
# we refresh proactively instead of racing a 401 mid-request.
_EXPIRY_SKEW_MS = 60_000


class RegisteredClient(BaseModel):
    """Result of OAuth 2.0 Dynamic Client Registration (RFC 7591)."""

    client_id: str
    client_secret: str | None = None


class TokenResponse(BaseModel):
    """Successful token endpoint response (RFC 6749 §5.1)."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600
    refresh_token: str | None = None
    scope: str | None = None


class McpOAuthState(BaseModel):
    """Persisted MCP OAuth credentials, stored separately from the mobile login.

    Lives at ``~/.config/coros-cli/mcp-oauth.json`` (mode 0600).
    """

    region: str = "eu"
    issuer: str
    client_id: str
    client_secret: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "Bearer"
    scope: str | None = None
    # Absolute access-token expiry, epoch milliseconds. 0 means "unknown".
    expires_at_ms: int = 0
    updated_at_ms: int = Field(default=0)

    @classmethod
    def from_token(
        cls,
        *,
        region: str,
        issuer: str,
        client: RegisteredClient,
        token: TokenResponse,
    ) -> McpOAuthState:
        now_ms = int(time.time() * 1000)
        return cls(
            region=region,
            issuer=issuer,
            client_id=client.client_id,
            client_secret=client.client_secret,
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            token_type=token.token_type,
            scope=token.scope,
            expires_at_ms=now_ms + token.expires_in * 1000,
            updated_at_ms=now_ms,
        )

    def with_token(self, token: TokenResponse) -> McpOAuthState:
        """Return a copy updated from a fresh token response (refresh flow)."""
        now_ms = int(time.time() * 1000)
        return self.model_copy(
            update={
                "access_token": token.access_token,
                # A refresh response may omit refresh_token; keep the old one.
                "refresh_token": token.refresh_token or self.refresh_token,
                "token_type": token.token_type,
                "scope": token.scope or self.scope,
                "expires_at_ms": now_ms + token.expires_in * 1000,
                "updated_at_ms": now_ms,
            }
        )

    def registered_client(self) -> RegisteredClient:
        return RegisteredClient(client_id=self.client_id, client_secret=self.client_secret)

    def access_expired(self, *, skew_ms: int = _EXPIRY_SKEW_MS) -> bool:
        if not self.access_token:
            return True
        if self.expires_at_ms == 0:
            return False
        return int(time.time() * 1000) + skew_ms >= self.expires_at_ms
