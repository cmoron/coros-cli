from __future__ import annotations

import re

from coros_cli.mcp.pkce import code_challenge, generate_code_verifier, generate_state

# Unpadded base64url alphabet (RFC 7636 §4.1).
_B64URL = re.compile(r"^[A-Za-z0-9_-]+$")


def test_code_verifier_is_valid_length_and_charset() -> None:
    verifier = generate_code_verifier()
    assert 43 <= len(verifier) <= 128
    assert _B64URL.match(verifier)


def test_code_verifier_is_random() -> None:
    assert generate_code_verifier() != generate_code_verifier()


def test_code_challenge_matches_rfc7636_test_vector() -> None:
    # RFC 7636 Appendix B worked example.
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert code_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_code_challenge_is_deterministic() -> None:
    verifier = generate_code_verifier()
    assert code_challenge(verifier) == code_challenge(verifier)


def test_state_is_random_and_base64url() -> None:
    state = generate_state()
    assert _B64URL.match(state)
    assert generate_state() != generate_state()
