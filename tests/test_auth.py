from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from coros_cli.auth import CorosAuthError, ensure_mobile_token, login, refresh_mobile_token
from coros_cli.endpoints import (
    MOBILE_BASE_URLS,
    MOBILE_LOGIN,
    WEB_ACCOUNT_QUERY,
    WEB_BASE_URLS,
    WEB_LOGIN,
)
from coros_cli.models import StoredAuth


def _ok_web_login(token: str = "web-tok") -> dict:
    return {"result": "0000", "data": {"accessToken": token, "userId": "u1"}}


def _ok_mobile_login(token: str = "mob-tok") -> dict:
    return {"result": "0000", "data": {"accessToken": token}}


def _ok_account_query() -> dict:
    return {"result": "0000", "data": {}}


def _wrong_region() -> dict:
    return {"result": "1019", "message": "wrong region"}


async def test_login_skips_mobile_by_default(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=WEB_BASE_URLS["eu"] + WEB_LOGIN, json=_ok_web_login())
    httpx_mock.add_response(url=WEB_BASE_URLS["eu"] + WEB_ACCOUNT_QUERY, json=_ok_account_query())

    auth = await login("user@example.com", "secret", region="eu")

    assert auth.region == "eu"
    assert auth.web_access_token == "web-tok"
    assert auth.mobile_access_token is None
    assert auth.mobile_login_payload is None
    assert auth.pwd_hash == "5ebe2294ecd0e0f08eab7690d2a6ee69"  # md5("secret")


async def test_login_with_mobile_flag(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=WEB_BASE_URLS["eu"] + WEB_LOGIN, json=_ok_web_login())
    httpx_mock.add_response(url=WEB_BASE_URLS["eu"] + WEB_ACCOUNT_QUERY, json=_ok_account_query())
    httpx_mock.add_response(url=MOBILE_BASE_URLS["eu"] + MOBILE_LOGIN, json=_ok_mobile_login())

    auth = await login("user@example.com", "secret", region="eu", with_mobile=True)

    assert auth.mobile_access_token == "mob-tok"
    assert auth.mobile_login_payload is not None


async def test_login_auto_corrects_region_to_us(httpx_mock: HTTPXMock) -> None:
    # Initial attempt on EU succeeds logging in, but account/query on EU returns 1019.
    httpx_mock.add_response(url=WEB_BASE_URLS["eu"] + WEB_LOGIN, json=_ok_web_login("tok-eu"))
    httpx_mock.add_response(url=WEB_BASE_URLS["eu"] + WEB_ACCOUNT_QUERY, json=_wrong_region())
    httpx_mock.add_response(url=WEB_BASE_URLS["us"] + WEB_ACCOUNT_QUERY, json=_ok_account_query())
    # Re-login on detected region
    httpx_mock.add_response(url=WEB_BASE_URLS["us"] + WEB_LOGIN, json=_ok_web_login("tok-us"))

    auth = await login("u@e.com", "pw", region="eu")

    assert auth.region == "us"
    assert auth.web_access_token == "tok-us"


async def test_ensure_mobile_token_is_noop_when_present() -> None:
    auth = StoredAuth(
        email="u@e.com",
        pwd_hash="h",
        mobile_access_token="tok",
        mobile_login_payload={"appKey": "k"},
    )
    assert await ensure_mobile_token(auth) is auth


async def test_ensure_mobile_token_performs_mobile_login(httpx_mock: HTTPXMock) -> None:
    auth = StoredAuth(email="u@e.com", pwd_hash="h", region="eu")
    httpx_mock.add_response(
        url=MOBILE_BASE_URLS["eu"] + MOBILE_LOGIN,
        json=_ok_mobile_login("fresh"),
    )
    updated = await ensure_mobile_token(auth)
    assert updated.mobile_access_token == "fresh"
    assert updated.mobile_login_payload is not None


async def test_login_raises_on_bad_credentials(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=WEB_BASE_URLS["eu"] + WEB_LOGIN,
        json={"result": "2009", "message": "wrong password"},
    )
    with pytest.raises(CorosAuthError, match="web login"):
        await login("u@e.com", "bad", region="eu")


async def test_refresh_mobile_token_replays_payload(httpx_mock: HTTPXMock) -> None:
    auth = StoredAuth(
        email="u@e.com",
        pwd_hash="h",
        region="eu",
        mobile_access_token="old",
        mobile_login_payload={"appKey": "k", "account": "e", "pwd": "p"},
    )
    httpx_mock.add_response(
        url=MOBILE_BASE_URLS["eu"] + MOBILE_LOGIN,
        json=_ok_mobile_login("fresh-tok"),
    )
    refreshed = await refresh_mobile_token(auth)
    assert refreshed.mobile_access_token == "fresh-tok"
    assert refreshed.timestamp_ms > 0


async def test_refresh_mobile_token_without_payload_raises() -> None:
    auth = StoredAuth(email="u@e.com", pwd_hash="h")
    with pytest.raises(CorosAuthError, match="no mobile login payload"):
        await refresh_mobile_token(auth)
