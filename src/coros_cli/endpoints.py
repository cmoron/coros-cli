from __future__ import annotations

from coros_cli.models import Region

WEB_BASE_URLS: dict[Region, str] = {
    "eu": "https://teameuapi.coros.com",
    "us": "https://teamapi.coros.com",
    "asia": "https://teamcnapi.coros.com",
    "cn": "https://teamcnapi.coros.com",
}

MOBILE_BASE_URLS: dict[Region, str] = {
    "eu": "https://apieu.coros.com",
    "us": "https://apius.coros.com",
    "asia": "https://apicn.coros.com",
    "cn": "https://apicn.coros.com",
}

# Coros API result codes
RESULT_SUCCESS = "0000"
RESULT_TOKEN_EXPIRED = "0102"
RESULT_TOKEN_INVALID = "0101"
RESULT_WRONG_REGION = "1019"

# Web endpoints
WEB_LOGIN = "/account/login"
WEB_ACCOUNT_QUERY = "/account/query"
WEB_ANALYSE_DAY_DETAIL = "/analyse/dayDetail/query"

# Mobile endpoints
MOBILE_LOGIN = "/coros/user/login"
MOBILE_SLEEP_DAILY = "/coros/data/statistic/daily"

TOKEN_TTL_MS = 24 * 60 * 60 * 1000
