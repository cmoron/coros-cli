from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from coros_cli.api.mobile import CorosApiError, fetch_sleep
from coros_cli.endpoints import (
    MOBILE_BASE_URLS,
    MOBILE_LOGIN,
    MOBILE_SLEEP_DAILY,
)
from coros_cli.models import StoredAuth


def _auth() -> StoredAuth:
    return StoredAuth(
        email="u@e.com",
        pwd_hash="h",
        region="eu",
        mobile_access_token="tok",
        mobile_login_payload={"appKey": "k"},
    )


def _sleep_response(days: list[dict]) -> dict:
    return {
        "result": "0000",
        "data": {"statisticData": {"dayDataList": days}},
    }


def _day(date: str, **overrides) -> dict:
    sd = {
        "totalSleepTime": 420,
        "deepTime": 90,
        "lightTime": 250,
        "eyeTime": 60,
        "wakeTime": 20,
        "shortSleepTime": 0,
        "avgHeartRate": 55,
        "minHeartRate": 48,
        "maxHeartRate": 72,
    }
    sd.update(overrides.pop("sleepData", {}))
    base = {"happenDay": int(date), "sleepData": sd}
    base.update(overrides)
    return base


async def test_fetch_sleep_parses_records(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{MOBILE_BASE_URLS['eu']}{MOBILE_SLEEP_DAILY}?accessToken=tok",
        json=_sleep_response([_day("20260410"), _day("20260411")]),
    )

    auth, records = await fetch_sleep(_auth(), "20260410", "20260411")

    assert auth.mobile_access_token == "tok"
    assert [r.date for r in records] == ["20260410", "20260411"]
    assert records[0].total_minutes == 420
    assert records[0].phases.deep_minutes == 90
    assert records[0].phases.rem_minutes == 60
    assert records[0].avg_hr == 55
    assert records[0].min_hr == 48
    assert records[0].max_hr == 72


async def test_fetch_sleep_sorts_by_date(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{MOBILE_BASE_URLS['eu']}{MOBILE_SLEEP_DAILY}?accessToken=tok",
        json=_sleep_response([_day("20260412"), _day("20260410"), _day("20260411")]),
    )
    _, records = await fetch_sleep(_auth(), "20260410", "20260412")
    assert [r.date for r in records] == ["20260410", "20260411", "20260412"]


async def test_fetch_sleep_refreshes_on_token_expired(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{MOBILE_BASE_URLS['eu']}{MOBILE_SLEEP_DAILY}?accessToken=tok",
        json={"result": "1019", "message": "token expired"},
    )
    httpx_mock.add_response(
        url=MOBILE_BASE_URLS["eu"] + MOBILE_LOGIN,
        json={"result": "0000", "data": {"accessToken": "fresh"}},
    )
    httpx_mock.add_response(
        url=f"{MOBILE_BASE_URLS['eu']}{MOBILE_SLEEP_DAILY}?accessToken=fresh",
        json=_sleep_response([_day("20260410")]),
    )

    auth, records = await fetch_sleep(_auth(), "20260410", "20260410")
    assert auth.mobile_access_token == "fresh"
    assert len(records) == 1


async def test_fetch_sleep_raises_on_api_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{MOBILE_BASE_URLS['eu']}{MOBILE_SLEEP_DAILY}?accessToken=tok",
        json={"result": "9999", "message": "nope"},
    )
    with pytest.raises(CorosApiError, match="9999"):
        await fetch_sleep(_auth(), "20260410", "20260410")


async def test_fetch_sleep_handles_empty_list(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{MOBILE_BASE_URLS['eu']}{MOBILE_SLEEP_DAILY}?accessToken=tok",
        json=_sleep_response([]),
    )
    _, records = await fetch_sleep(_auth(), "20260410", "20260410")
    assert records == []


async def test_fetch_sleep_merges_hrv_when_userid_present(httpx_mock: HTTPXMock) -> None:
    from coros_cli.endpoints import WEB_ANALYSE_DAY_DETAIL, WEB_BASE_URLS

    auth = _auth().model_copy(update={"user_id": "u1", "web_access_token": "web"})
    httpx_mock.add_response(
        url=f"{MOBILE_BASE_URLS['eu']}{MOBILE_SLEEP_DAILY}?accessToken=tok",
        json=_sleep_response([_day("20260410"), _day("20260411")]),
    )
    httpx_mock.add_response(
        url=f"{WEB_BASE_URLS['eu']}{WEB_ANALYSE_DAY_DETAIL}?startDay=20260410&endDay=20260411",
        json={
            "result": "0000",
            "data": {
                "dayList": [
                    {
                        "happenDay": 20260410,
                        "avgSleepHrv": 58,
                        "sleepHrvBase": 55,
                        "sleepHrvIntervalList": [30, 45, 50, 65],
                    },
                    {
                        "happenDay": 20260411,
                        "avgSleepHrv": 0,
                        "sleepHrvBase": 0,
                        "sleepHrvIntervalList": [],
                    },
                ]
            },
        },
    )

    _, records = await fetch_sleep(auth, "20260410", "20260411")
    assert records[0].hrv_avg == 58
    assert records[1].hrv_avg is None  # empty HRV row not merged


async def test_fetch_sleep_ignores_hrv_failure(httpx_mock: HTTPXMock) -> None:
    from coros_cli.endpoints import WEB_ANALYSE_DAY_DETAIL, WEB_BASE_URLS

    auth = _auth().model_copy(update={"user_id": "u1", "web_access_token": "web"})
    httpx_mock.add_response(
        url=f"{MOBILE_BASE_URLS['eu']}{MOBILE_SLEEP_DAILY}?accessToken=tok",
        json=_sleep_response([_day("20260410")]),
    )
    httpx_mock.add_response(
        url=f"{WEB_BASE_URLS['eu']}{WEB_ANALYSE_DAY_DETAIL}?startDay=20260410&endDay=20260410",
        json={"result": "0101", "message": "token invalid"},
    )
    _, records = await fetch_sleep(auth, "20260410", "20260410")
    assert len(records) == 1
    assert records[0].hrv_avg is None
