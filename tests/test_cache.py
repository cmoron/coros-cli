from __future__ import annotations

import time
from pathlib import Path

import pytest

from coros_cli.cache import (
    SleepCache,
    load_sleep_cache,
    merge_records,
    save_sleep_cache,
    sleep_cache_path,
)
from coros_cli.models import SleepPhases, SleepRecord


@pytest.fixture
def tmp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def _rec(date: str, hrv: int | None = None) -> SleepRecord:
    return SleepRecord(
        date=date,
        total_minutes=420,
        phases=SleepPhases(deep_minutes=90, light_minutes=250, rem_minutes=60, awake_minutes=20),
        avg_hr=55,
        hrv_avg=hrv,
    )


def test_empty_cache_is_stale() -> None:
    cache = SleepCache()
    assert cache.is_stale()
    assert cache.age_days() == float("inf")


def test_fresh_cache_is_not_stale() -> None:
    cache = SleepCache(synced_at_ms=int(time.time() * 1000))
    assert not cache.is_stale(7.0)
    assert cache.age_days() < 0.1


def test_stale_after_ttl() -> None:
    eight_days_ago = int((time.time() - 8 * 86400) * 1000)
    cache = SleepCache(synced_at_ms=eight_days_ago)
    assert cache.is_stale(7.0)
    assert not cache.is_stale(10.0)


def test_covers_inclusive_range() -> None:
    cache = SleepCache(records={"20260410": _rec("20260410"), "20260411": _rec("20260411")})
    assert cache.covers("20260410", "20260411")
    assert not cache.covers("20260409", "20260411")
    assert not cache.covers("20260410", "20260412")


def test_in_range_filters_and_sorts() -> None:
    cache = SleepCache(
        records={
            "20260412": _rec("20260412"),
            "20260410": _rec("20260410"),
            "20260411": _rec("20260411"),
            "20260501": _rec("20260501"),
        }
    )
    records = cache.in_range("20260410", "20260412")
    assert [r.date for r in records] == ["20260410", "20260411", "20260412"]


def test_merge_records_overwrites_and_adds(tmp_config: Path) -> None:
    cache = SleepCache(records={"20260410": _rec("20260410", hrv=50)})
    updated = merge_records(cache, [_rec("20260410", hrv=55), _rec("20260411", hrv=60)])
    assert updated.records["20260410"].hrv_avg == 55
    assert updated.records["20260411"].hrv_avg == 60
    assert updated.synced_at_ms > 0


def test_save_and_load_roundtrip(tmp_config: Path) -> None:
    cache = SleepCache(synced_at_ms=12345, records={"20260410": _rec("20260410", hrv=58)})
    save_sleep_cache(cache)
    assert sleep_cache_path().exists()
    loaded = load_sleep_cache()
    assert loaded.synced_at_ms == 12345
    assert loaded.records["20260410"].hrv_avg == 58


def test_load_missing_returns_empty(tmp_config: Path) -> None:
    cache = load_sleep_cache()
    assert cache.synced_at_ms == 0
    assert cache.records == {}


def test_load_corrupted_returns_empty(tmp_config: Path) -> None:
    path = sleep_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json {{{")
    cache = load_sleep_cache()
    assert cache.synced_at_ms == 0
