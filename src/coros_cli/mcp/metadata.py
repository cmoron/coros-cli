from __future__ import annotations

from dataclasses import dataclass

from coros_cli.models import Region

# OAuth scopes requested for the authorization-code grant. `offline_access`
# asks the server for a refresh token.
MCP_SCOPES: tuple[str, ...] = ("openid", "mcp.tools", "offline_access")


@dataclass(frozen=True, slots=True)
class McpServerMetadata:
    """Resolved OAuth + MCP endpoints for a COROS MCP server.

    Endpoints follow a fixed path convention off the issuer. Keeping them as
    explicit fields (rather than re-deriving on use) leaves room to later swap
    in values discovered via ``/.well-known/oauth-authorization-server``.
    """

    region: Region
    issuer: str
    registration_endpoint: str
    authorization_endpoint: str
    token_endpoint: str
    revocation_endpoint: str
    mcp_endpoint: str
    scopes: tuple[str, ...] = MCP_SCOPES

    @property
    def scope_param(self) -> str:
        return " ".join(self.scopes)


def _from_issuer(region: Region, issuer: str) -> McpServerMetadata:
    issuer = issuer.rstrip("/")
    return McpServerMetadata(
        region=region,
        issuer=issuer,
        registration_endpoint=f"{issuer}/connect/register",
        authorization_endpoint=f"{issuer}/oauth2/authorize",
        token_endpoint=f"{issuer}/oauth2/token",
        revocation_endpoint=f"{issuer}/oauth2/revoke",
        mcp_endpoint=f"{issuer}/mcp",
    )


# Known MCP issuers per region. COROS documents NA/else, Europe and China MCP
# hosts; there is no public dedicated Asia endpoint, so `asia` falls back to
# the NA/else (`us`) host below.
MCP_ISSUERS: dict[Region, str] = {
    "us": "https://mcpus.coros.com",
    "eu": "https://mcpeu.coros.com",
    "cn": "https://mcpcn.coros.com",
}

# Region used when no dedicated issuer exists (currently only `asia`). COROS
# only documents NA/else, Europe and China hosts, so route Asia to the NA/else
# (`us`) host rather than EU.
_FALLBACK_REGION: Region = "us"


def metadata_for_region(region: Region) -> McpServerMetadata:
    """Resolve MCP server metadata for a region, falling back to the NA/else host."""
    issuer = MCP_ISSUERS.get(region) or MCP_ISSUERS[_FALLBACK_REGION]
    return _from_issuer(region, issuer)
