from __future__ import annotations

import pytest

from coros_cli.mcp.metadata import metadata_for_region
from coros_cli.models import Region


@pytest.mark.parametrize(
    ("region", "issuer"),
    [
        ("us", "https://mcpus.coros.com"),
        ("eu", "https://mcpeu.coros.com"),
        ("cn", "https://mcpcn.coros.com"),
    ],
)
def test_metadata_resolves_known_region(region: Region, issuer: str) -> None:
    meta = metadata_for_region(region)
    assert meta.region == region
    assert meta.issuer == issuer
    assert meta.mcp_endpoint == f"{issuer}/mcp"
    assert meta.authorization_endpoint == f"{issuer}/oauth2/authorize"
    assert meta.token_endpoint == f"{issuer}/oauth2/token"


def test_asia_falls_back_to_us_host() -> None:
    """No public Asia endpoint exists; Asia routes to the NA/else (us) host."""
    asia = metadata_for_region("asia")
    us = metadata_for_region("us")
    assert asia.region == "asia"
    assert asia.issuer == us.issuer == "https://mcpus.coros.com"
    assert asia.mcp_endpoint == "https://mcpus.coros.com/mcp"
