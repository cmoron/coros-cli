from __future__ import annotations

import base64
import hashlib

from Crypto.Cipher import AES

_MOBILE_AES_IV = b"weloop3_2015_03#"


def md5_hex(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()


def mobile_encrypt(plaintext: str, app_key: str) -> str:
    """Encrypt a payload for the Coros mobile login API.

    Scheme reverse-engineered from libencrypt-lib.so in the Coros Android APK:
      1. XOR plaintext bytes with app_key bytes cyclically
      2. PKCS7-pad to 16-byte boundary
      3. AES-128-CBC: key = app_key bytes, IV = b"weloop3_2015_03#"
      4. Base64-encode
    """
    key = app_key.encode("ascii")
    if len(key) != 16:
        raise ValueError("app_key must be 16 ASCII bytes")
    data = plaintext.encode("utf-8")
    xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    pad_len = 16 - (len(xored) % 16)
    padded = xored + bytes([pad_len] * pad_len)
    cipher = AES.new(key, AES.MODE_CBC, _MOBILE_AES_IV)
    return base64.b64encode(cipher.encrypt(padded)).decode("ascii")
