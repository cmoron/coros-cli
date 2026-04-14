from __future__ import annotations

import asyncio

import httpx

from coros_cli.api.web import CorosWebApiError, fetch_hrv_by_day
from coros_cli.auth import CorosAuthError, ensure_mobile_token, refresh_mobile_token
from coros_cli.endpoints import (
    MOBILE_BASE_URLS,
    MOBILE_SLEEP_DAILY,
    RESULT_SUCCESS,
    RESULT_TOKEN_EXPIRED,
    RESULT_TOKEN_INVALID,
    RESULT_WRONG_REGION,
)
from coros_cli.models import SleepPhases, SleepRecord, StoredAuth


class CorosApiError(Exception):
    pass


_EXPIRED_CODES = {RESULT_TOKEN_EXPIRED, RESULT_TOKEN_INVALID, RESULT_WRONG_REGION}


def _parse_record(item: dict) -> SleepRecord:
    sd = item.get("sleepData") or {}
    return SleepRecord(
        date=str(item.get("happenDay", "")),
        total_minutes=sd.get("totalSleepTime"),
        phases=SleepPhases(
            deep_minutes=sd.get("deepTime"),
            light_minutes=sd.get("lightTime"),
            rem_minutes=sd.get("eyeTime"),
            awake_minutes=sd.get("wakeTime"),
            nap_minutes=sd.get("shortSleepTime") or None,
        ),
        avg_hr=sd.get("avgHeartRate"),
        min_hr=sd.get("minHeartRate"),
        max_hr=sd.get("maxHeartRate"),
    )


async def _post_sleep(client: httpx.AsyncClient, auth: StoredAuth, payload: dict) -> dict:
    url = MOBILE_BASE_URLS[auth.region] + MOBILE_SLEEP_DAILY
    token = auth.mobile_access_token
    if not token:
        raise CorosApiError("no mobile token; run `coros login`")
    resp = await client.post(
        url,
        params={"accessToken": token},
        json=payload,
        headers={"Content-Type": "application/json", "accesstoken": token},
    )
    resp.raise_for_status()
    return resp.json()


async def _fetch_sleep_records(
    auth: StoredAuth, start_day: str, end_day: str
) -> tuple[StoredAuth, list[SleepRecord]]:
    auth = await ensure_mobile_token(auth)

    payload = {
        "allDeviceSleep": 1,
        "dataType": [5],
        "dataVersion": 0,
        "startTime": int(start_day),
        "endTime": int(end_day),
        "statisticType": 1,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        body = await _post_sleep(client, auth, payload)
        code = body.get("result")
        if code in _EXPIRED_CODES:
            auth = await refresh_mobile_token(auth)
            body = await _post_sleep(client, auth, payload)
            code = body.get("result")
        if code != RESULT_SUCCESS:
            raise CorosApiError(f"sleep API: [{code}] {body.get('message', body)}")

    items = body.get("data", {}).get("statisticData", {}).get("dayDataList", []) or []
    records = [_parse_record(item) for item in items]
    records.sort(key=lambda r: r.date)
    return auth, records


async def fetch_sleep(
    auth: StoredAuth, start_day: str, end_day: str
) -> tuple[StoredAuth, list[SleepRecord]]:
    """Fetch sleep records + HRV for a YYYYMMDD date range.

    Sleep stages come from the mobile API (triggers lazy mobile login, which
    disconnects the Coros phone app). HRV comes from the web API in parallel
    and has no mobile-session impact. HRV rows missing userId just return
    without HRV — we do not fail the whole command.
    """
    import sys

    sleep_task = asyncio.create_task(_fetch_sleep_records(auth, start_day, end_day))
    hrv_task: asyncio.Task[dict[str, int]] | None = None
    if auth.user_id:
        hrv_task = asyncio.create_task(fetch_hrv_by_day(auth, start_day, end_day))
    else:
        print("[hrv] skipped: no user_id on stored auth — re-run `coros login`", file=sys.stderr)

    auth, records = await sleep_task

    hrv_map: dict[str, int] = {}
    if hrv_task is not None:
        try:
            hrv_map = await hrv_task
        except CorosWebApiError as e:
            print(f"[hrv] web fetch failed: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[hrv] unexpected error: {type(e).__name__}: {e}", file=sys.stderr)
        else:
            if not hrv_map:
                print(
                    f"[hrv] API returned no HRV for {start_day}..{end_day} "
                    "(dayList empty or all avgSleepHrv=0)",
                    file=sys.stderr,
                )

    if hrv_map:
        records = [r.model_copy(update={"hrv_avg": hrv_map.get(r.date)}) for r in records]

    return auth, records


__all__ = ["CorosApiError", "CorosAuthError", "fetch_sleep"]
