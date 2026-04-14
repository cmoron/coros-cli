from __future__ import annotations

import base64

import pytest
from Crypto.Cipher import AES

from coros_cli.crypto import _MOBILE_AES_IV, md5_hex, mobile_encrypt


def _decrypt(ciphertext_b64: str, app_key: str) -> str:
    """Reverse of mobile_encrypt — used only for round-trip testing."""
    key = app_key.encode("ascii")
    cipher = AES.new(key, AES.MODE_CBC, _MOBILE_AES_IV)
    padded = cipher.decrypt(base64.b64decode(ciphertext_b64))
    pad_len = padded[-1]
    xored = padded[:-pad_len]
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(xored)).decode("utf-8")


def test_md5_hex_known_vector() -> None:
    assert md5_hex("hello") == "5d41402abc4b2a76b9719d911017c592"


def test_mobile_encrypt_round_trip_email() -> None:
    key = "1234567890123456"
    assert _decrypt(mobile_encrypt("user@example.com", key), key) == "user@example.com"


def test_mobile_encrypt_round_trip_unicode() -> None:
    key = "abcdefghijklmnop"
    plaintext = "héllo-wörld-🔒"
    assert _decrypt(mobile_encrypt(plaintext, key), key) == plaintext


def test_mobile_encrypt_deterministic_for_same_key() -> None:
    key = "1234567890123456"
    assert mobile_encrypt("foo", key) == mobile_encrypt("foo", key)


def test_mobile_encrypt_rejects_non_16_byte_key() -> None:
    with pytest.raises(ValueError):
        mobile_encrypt("foo", "short")
