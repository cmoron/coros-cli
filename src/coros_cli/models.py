from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Region = Literal["eu", "us", "asia", "cn"]


class StoredAuth(BaseModel):
    email: str
    pwd_hash: str
    region: Region = "eu"
    web_access_token: str | None = None
    mobile_access_token: str | None = None
    mobile_login_payload: dict | None = None
    timestamp_ms: int = 0


class SleepPhases(BaseModel):
    deep_minutes: int | None = None
    light_minutes: int | None = None
    rem_minutes: int | None = None
    awake_minutes: int | None = None
    nap_minutes: int | None = None


class SleepRecord(BaseModel):
    date: str = Field(description="YYYYMMDD")
    total_minutes: int | None = None
    phases: SleepPhases = Field(default_factory=SleepPhases)
    avg_hr: int | None = None
    min_hr: int | None = None
    max_hr: int | None = None
