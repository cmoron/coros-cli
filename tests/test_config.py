from __future__ import annotations

from pathlib import Path

import pytest

from coros_cli.config import config_path, load_auth, save_auth
from coros_cli.models import StoredAuth


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))


def test_load_returns_none_when_missing() -> None:
    assert load_auth() is None


def test_save_then_load_round_trip() -> None:
    auth = StoredAuth(
        email="a@b.c",
        pwd_hash="deadbeef",
        region="eu",
        web_access_token="tok",
        mobile_access_token="mtok",
        timestamp_ms=42,
    )
    save_auth(auth)
    loaded = load_auth()
    assert loaded == auth


def test_save_writes_to_xdg_path() -> None:
    save_auth(StoredAuth(email="a@b.c", pwd_hash="x"))
    assert config_path().exists()
    assert config_path().name == "config.json"
