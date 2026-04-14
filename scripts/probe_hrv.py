"""Dump the raw /analyse/dayDetail/query response to diagnose HRV extraction.

Usage: uv run python scripts/probe_hrv.py [start_day] [end_day]
       start_day/end_day as YYYYMMDD, default last 7 days.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta

import httpx

from coros_cli.config import load_auth
from coros_cli.endpoints import WEB_ANALYSE_DAY_DETAIL, WEB_BASE_URLS


def main() -> None:
    auth = load_auth()
    if auth is None:
        sys.exit("Not logged in. Run: coros login")

    today = date.today()
    start = sys.argv[1] if len(sys.argv) > 1 else (today - timedelta(days=6)).strftime("%Y%m%d")
    end = sys.argv[2] if len(sys.argv) > 2 else today.strftime("%Y%m%d")

    if not auth.user_id:
        print(f"[warn] user_id is missing on stored auth. region={auth.region}")
        print("[warn] re-run `coros login` to capture it, then rerun this probe.")

    url = WEB_BASE_URLS[auth.region] + WEB_ANALYSE_DAY_DETAIL
    headers = {
        "accessToken": auth.web_access_token or "",
        "accesstoken": auth.web_access_token or "",
        "Accept": "application/json, text/plain, */*",
    }
    if auth.user_id:
        headers["yfheader"] = json.dumps({"userId": auth.user_id}, separators=(",", ":"))

    print(f"GET {url}?startDay={start}&endDay={end}")
    print(f"headers: {list(headers)}")
    print(f"user_id: {auth.user_id!r}")
    print("---")

    resp = httpx.get(url, params={"startDay": start, "endDay": end}, headers=headers, timeout=30)
    print(f"HTTP {resp.status_code}")
    try:
        body = resp.json()
    except Exception:
        print(resp.text[:2000])
        return

    print(json.dumps(body, indent=2, ensure_ascii=False)[:6000])


if __name__ == "__main__":
    main()
