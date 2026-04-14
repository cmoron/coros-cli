from __future__ import annotations

import json

import httpx

from coros_cli.endpoints import (
    RESULT_SUCCESS,
    RESULT_TOKEN_EXPIRED,
    RESULT_TOKEN_INVALID,
    RESULT_WRONG_REGION,
    WEB_ANALYSE_DAY_DETAIL,
    WEB_BASE_URLS,
)
from coros_cli.models import StoredAuth


class CorosWebApiError(Exception):
    pass


_EXPIRED_CODES = {RESULT_TOKEN_EXPIRED, RESULT_TOKEN_INVALID, RESULT_WRONG_REGION}


def _headers(auth: StoredAuth) -> dict[str, str]:
    if not auth.web_access_token:
        raise CorosWebApiError("no web token; run `coros login`")
    if not auth.user_id:
        raise CorosWebApiError("no userId stored; re-run `coros login` to capture it")
    return {
        "accessToken": auth.web_access_token,
        "accesstoken": auth.web_access_token,
        "yfheader": json.dumps({"userId": auth.user_id}, separators=(",", ":")),
        "Accept": "application/json, text/plain, */*",
    }


async def fetch_hrv_by_day(auth: StoredAuth, start_day: str, end_day: str) -> dict[str, int]:
    """Return {YYYYMMDD: avgSleepHrv_ms} via /analyse/dayDetail/query (web API).

    Only the overnight average HRV (rmssd) is extracted. Days with no reading
    or a 0/missing value are omitted. No mobile-session impact.
    """
    url = WEB_BASE_URLS[auth.region] + WEB_ANALYSE_DAY_DETAIL
    params = {"startDay": start_day, "endDay": end_day}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params, headers=_headers(auth))
        resp.raise_for_status()
        body = resp.json()

    code = body.get("result") or body.get("apiCode")
    if code in _EXPIRED_CODES:
        raise CorosWebApiError(f"web token expired ({code}); run `coros login` again")
    if code != RESULT_SUCCESS:
        raise CorosWebApiError(f"dayDetail: [{code}] {body.get('message', body)}")

    out: dict[str, int] = {}
    for item in body.get("data", {}).get("dayList", []) or []:
        day = item.get("happenDay")
        avg = item.get("avgSleepHrv")
        if day is None or not avg:
            continue
        out[str(day)] = int(avg)
    return out


__all__ = ["CorosWebApiError", "fetch_hrv_by_day"]
