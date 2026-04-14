from __future__ import annotations

import json
import time
from pathlib import Path

from pydantic import BaseModel, Field

from coros_cli.config import config_dir
from coros_cli.models import SleepRecord


class SleepCache(BaseModel):
    synced_at_ms: int = 0
    records: dict[str, SleepRecord] = Field(default_factory=dict)

    def age_days(self) -> float:
        if self.synced_at_ms == 0:
            return float("inf")
        return (time.time() * 1000 - self.synced_at_ms) / (1000 * 60 * 60 * 24)

    def is_stale(self, ttl_days: float = 7.0) -> bool:
        return self.age_days() > ttl_days

    def covers(self, start_day: str, end_day: str) -> bool:
        """True iff every YYYYMMDD in [start_day, end_day] (inclusive) is cached."""
        from datetime import datetime, timedelta

        d = datetime.strptime(start_day, "%Y%m%d")
        end = datetime.strptime(end_day, "%Y%m%d")
        while d <= end:
            if d.strftime("%Y%m%d") not in self.records:
                return False
            d += timedelta(days=1)
        return True

    def in_range(self, start_day: str, end_day: str) -> list[SleepRecord]:
        return sorted(
            (r for d, r in self.records.items() if start_day <= d <= end_day),
            key=lambda r: r.date,
        )


def sleep_cache_path() -> Path:
    return config_dir() / "data" / "sleep.json"


def load_sleep_cache() -> SleepCache:
    path = sleep_cache_path()
    if not path.exists():
        return SleepCache()
    try:
        return SleepCache.model_validate_json(path.read_text())
    except (json.JSONDecodeError, ValueError):
        return SleepCache()


def save_sleep_cache(cache: SleepCache) -> None:
    path = sleep_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cache.model_dump_json(indent=2))
    path.chmod(0o600)


def merge_records(cache: SleepCache, records: list[SleepRecord]) -> SleepCache:
    merged = dict(cache.records)
    for r in records:
        merged[r.date] = r
    return SleepCache(synced_at_ms=int(time.time() * 1000), records=merged)
