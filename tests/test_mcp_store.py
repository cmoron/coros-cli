from __future__ import annotations

import stat
from pathlib import Path

import pytest

from coros_cli.mcp.models import McpOAuthState
from coros_cli.mcp.store import (
    clear_mcp_state,
    load_mcp_state,
    mcp_oauth_path,
    save_mcp_state,
)


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))


def _state() -> McpOAuthState:
    return McpOAuthState(
        region="eu",
        issuer="https://mcpeu.coros.com",
        client_id="client-123",
        client_secret=None,
        access_token="acc",
        refresh_token="ref",
        scope="openid mcp.tools offline_access",
        expires_at_ms=10_000,
    )


def test_load_returns_none_when_missing() -> None:
    assert load_mcp_state() is None


def test_save_then_load_round_trip() -> None:
    state = _state()
    save_mcp_state(state)
    assert load_mcp_state() == state


def test_save_writes_separate_0600_file() -> None:
    save_mcp_state(_state())
    path = mcp_oauth_path()
    assert path.name == "mcp-oauth.json"
    assert path.exists()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_clear_removes_file() -> None:
    save_mcp_state(_state())
    assert clear_mcp_state() is True
    assert load_mcp_state() is None
    assert clear_mcp_state() is False


def test_load_tolerates_corrupt_file() -> None:
    path = mcp_oauth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json")
    assert load_mcp_state() is None
