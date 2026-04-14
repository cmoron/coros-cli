from __future__ import annotations

import json
import random
import time
from typing import Any

import httpx

from coros_cli.crypto import md5_hex, mobile_encrypt
from coros_cli.endpoints import (
    MOBILE_BASE_URLS,
    MOBILE_LOGIN,
    RESULT_SUCCESS,
    RESULT_WRONG_REGION,
    WEB_ACCOUNT_QUERY,
    WEB_BASE_URLS,
    WEB_LOGIN,
)
from coros_cli.models import Region, StoredAuth


class CorosAuthError(Exception):
    pass


_WEB_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)


def _check_ok(body: dict, context: str) -> None:
    code = body.get("result") or body.get("apiCode")
    if code != RESULT_SUCCESS:
        raise CorosAuthError(f"{context}: [{code}] {body.get('message', body)}")


async def _web_login(client: httpx.AsyncClient, region: Region, email: str, pwd_hash: str) -> str:
    resp = await client.post(
        WEB_BASE_URLS[region] + WEB_LOGIN,
        json={"account": email, "accountType": 2, "pwd": pwd_hash},
        headers={"Content-Type": "application/json", "User-Agent": _WEB_USER_AGENT},
    )
    resp.raise_for_status()
    body = resp.json()
    _check_ok(body, "web login")
    token = body.get("data", {}).get("accessToken")
    if not token:
        raise CorosAuthError("web login: no accessToken in response")
    return token


async def _detect_region(client: httpx.AsyncClient, web_token: str) -> Region:
    for region, base in WEB_BASE_URLS.items():
        resp = await client.get(base + WEB_ACCOUNT_QUERY, headers={"accesstoken": web_token})
        if resp.status_code != 200:
            continue
        body = resp.json()
        code = body.get("result") or body.get("apiCode")
        if code != RESULT_WRONG_REGION:
            return region
    return "eu"


def _build_mobile_payload(email: str, pwd_hash: str, app_key: str) -> dict[str, Any]:
    return {
        "account": mobile_encrypt(email, app_key) + "\n",
        "accountType": 2,
        "appKey": app_key,
        "clientType": 1,
        "hasHrCalibrated": 0,
        "kbValidity": 0,
        "pwd": mobile_encrypt(pwd_hash, app_key) + "\n",
        "region": "310|Europe/Berlin|US",
        "skipValidation": False,
    }


def _mobile_headers() -> dict[str, str]:
    yfheader = json.dumps(
        {
            "appVersion": 1125917087236096,
            "clientType": 1,
            "language": "en-US",
            "mobileName": "sdk_gphone64_arm64,google,Google",
            "releaseType": 1,
            "systemVersion": "13",
            "timezone": 4,
            "versionCode": "404080400",
        },
        separators=(",", ":"),
    )
    return {
        "content-type": "application/json",
        "accept-encoding": "gzip",
        "user-agent": "okhttp/4.12.0",
        "request-time": str(int(time.time() * 1000)),
        "yfheader": yfheader,
    }


def _random_app_key() -> str:
    return str(random.randint(1_000_000_000_000_000, 9_999_999_999_999_999))


async def _mobile_login_from_hash(
    client: httpx.AsyncClient, region: Region, email: str, pwd_hash: str
) -> tuple[str, dict[str, Any]]:
    payload = _build_mobile_payload(email, pwd_hash, _random_app_key())
    resp = await client.post(
        MOBILE_BASE_URLS[region] + MOBILE_LOGIN,
        json=payload,
        headers=_mobile_headers(),
    )
    resp.raise_for_status()
    body = resp.json()
    _check_ok(body, "mobile login")
    token = body.get("data", {}).get("accessToken")
    if not token:
        raise CorosAuthError("mobile login: no accessToken in response")
    return token, payload


async def login(
    email: str, password: str, region: Region = "eu", *, with_mobile: bool = False
) -> StoredAuth:
    """Authenticate against the Coros web API (and optionally mobile).

    Region is auto-corrected by pinging /account/query after web login.

    By default the mobile API login is skipped — it invalidates the user's
    Coros mobile app session. Set `with_mobile=True` to force it at login time,
    otherwise it is performed lazily on the first call that needs it.
    """
    pwd_hash = md5_hex(password)
    async with httpx.AsyncClient(timeout=30) as client:
        web_token = await _web_login(client, region, email, pwd_hash)
        detected = await _detect_region(client, web_token)
        if detected != region:
            region = detected
            web_token = await _web_login(client, region, email, pwd_hash)

        mobile_token: str | None = None
        mobile_payload: dict[str, Any] | None = None
        if with_mobile:
            mobile_token, mobile_payload = await _mobile_login_from_hash(
                client, region, email, pwd_hash
            )

    return StoredAuth(
        email=email,
        pwd_hash=pwd_hash,
        region=region,
        web_access_token=web_token,
        mobile_access_token=mobile_token,
        mobile_login_payload=mobile_payload,
        timestamp_ms=int(time.time() * 1000),
    )


async def ensure_mobile_token(auth: StoredAuth) -> StoredAuth:
    """Perform mobile login lazily using the stored pwd_hash.

    WARNING: this invalidates the user's Coros mobile app session.
    Callers should warn the user before invoking this.
    """
    if auth.mobile_access_token and auth.mobile_login_payload:
        return auth
    async with httpx.AsyncClient(timeout=30) as client:
        token, payload = await _mobile_login_from_hash(
            client, auth.region, auth.email, auth.pwd_hash
        )
    return auth.model_copy(
        update={
            "mobile_access_token": token,
            "mobile_login_payload": payload,
            "timestamp_ms": int(time.time() * 1000),
        }
    )


async def refresh_mobile_token(auth: StoredAuth) -> StoredAuth:
    """Replay the stored mobile login payload to refresh the mobile token.

    The stored payload includes appKey + already-encrypted credentials, so we
    can replay it without re-hashing the password.
    """
    if not auth.mobile_login_payload:
        raise CorosAuthError("no mobile login payload stored; run `coros login` again")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            MOBILE_BASE_URLS[auth.region] + MOBILE_LOGIN,
            json=auth.mobile_login_payload,
            headers=_mobile_headers(),
        )
        resp.raise_for_status()
        body = resp.json()
        _check_ok(body, "mobile refresh")
        token = body.get("data", {}).get("accessToken")
        if not token:
            raise CorosAuthError("mobile refresh: no accessToken in response")
    return auth.model_copy(
        update={"mobile_access_token": token, "timestamp_ms": int(time.time() * 1000)}
    )
