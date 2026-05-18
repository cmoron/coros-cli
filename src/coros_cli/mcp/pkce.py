"""PKCE (RFC 7636) helpers for the OAuth 2.0 authorization-code flow."""

from __future__ import annotations

import base64
import hashlib
import secrets


def _b64url(data: bytes) -> str:
    """Base64url-encode without padding, as required for PKCE values."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_code_verifier() -> str:
    """Generate a PKCE ``code_verifier`` (RFC 7636 §4.1).

    32 random bytes encode to a 43-character base64url string, comfortably
    inside the spec's 43-128 character range.
    """
    return _b64url(secrets.token_bytes(32))


def code_challenge(verifier: str) -> str:
    """Derive the S256 ``code_challenge`` from a verifier (RFC 7636 §4.2)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return _b64url(digest)


def generate_state() -> str:
    """Generate an opaque OAuth ``state`` value for CSRF protection."""
    return _b64url(secrets.token_bytes(16))
