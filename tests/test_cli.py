from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from coros_cli import cli
from coros_cli.mcp import runner

runner_cli = CliRunner()


@pytest.fixture()
def captured_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    """Replace runner.call_tool with a stub that records its inputs.

    Each command under test ends up calling runner.call_tool(tool, args); the
    stub returns a stable text result so we can also assert on rendering.
    """
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_call_tool(tool: str, args: dict[str, Any]) -> dict[str, Any]:
        calls.append((tool, args))
        return {
            "content": [{"type": "text", "text": '"ok"'}],
            "isError": False,
        }

    # Patch on both the runner module (canonical) and cli.run's binding.
    monkeypatch.setattr(runner, "call_tool", fake_call_tool)
    # Force a deterministic default timezone so we can assert on it.
    monkeypatch.setattr(runner, "default_timezone", lambda: "Europe/Paris")
    return calls


def _invoke(*args: str) -> Any:
    return runner_cli.invoke(cli.app, list(args))


def test_help_lists_top_level_commands() -> None:
    result = _invoke("--help")
    assert result.exit_code == 0
    for cmd in ("auth", "profile", "sleep", "hrv", "activities", "analyze", "mcp"):
        assert cmd in result.stdout


def test_profile_calls_query_user_info(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    result = _invoke("profile")
    assert result.exit_code == 0, result.stderr
    assert captured_calls == [("queryUserInfo", {})]
    assert "ok" in result.stdout


def test_sleep_passes_date_range_and_default_tz(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    result = _invoke("sleep", "--days", "3", "--to", "2026-05-25")
    assert result.exit_code == 0
    tool, args = captured_calls[0]
    assert tool == "querySleepData"
    assert args["endDate"] == "20260525"
    assert args["startDate"] == "20260523"
    assert args["days"] == 3
    assert args["timezone"] == "Europe/Paris"


def test_sleep_explicit_tz_overrides_default(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    result = _invoke("sleep", "--days", "1", "--tz", "Asia/Tokyo")
    assert result.exit_code == 0
    assert captured_calls[0][1]["timezone"] == "Asia/Tokyo"


def test_hrv_passes_days_and_tz(captured_calls: list[tuple[str, dict[str, Any]]]) -> None:
    _invoke("hrv", "--days", "14")
    assert captured_calls == [("queryHrvAssessment", {"days": 14, "timezone": "Europe/Paris"})]


def test_load_passes_days_only(captured_calls: list[tuple[str, dict[str, Any]]]) -> None:
    _invoke("load", "--days", "5")
    assert captured_calls == [("queryTrainingLoadAssessment", {"days": 5})]


def test_recovery_takes_no_arguments(captured_calls: list[tuple[str, dict[str, Any]]]) -> None:
    _invoke("recovery")
    assert captured_calls == [("queryRecoveryStatus", {})]


def test_activities_resolves_sport_group(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    _invoke("activities", "--days", "7", "--sport", "run", "--limit", "5")
    tool, args = captured_calls[0]
    assert tool == "querySportRecords"
    assert args["sportTypeCodes"] == [100, 101, 102, 103, 104, 105, 106]
    assert args["limit"] == 5


def test_activities_accepts_numeric_and_csv_sports(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    _invoke("activities", "--sport", "100,bike,300", "--limit", "10")
    args = captured_calls[0][1]
    assert args["sportTypeCodes"] == [100, 200, 201, 202, 203, 204, 205, 299, 300]


def test_activities_rejects_unknown_sport(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    result = _invoke("activities", "--sport", "nope")
    assert result.exit_code != 0
    assert captured_calls == []


def test_activities_defaults_to_all_when_unspecified(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    _invoke("activities", "--days", "1")
    assert captured_calls[0][1]["sportTypeCodes"] == [65535]


def test_activity_requires_sport_type(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    result = _invoke("activity", "label-1")
    assert result.exit_code != 0
    assert captured_calls == []


def test_activity_passes_label_and_sport(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    _invoke("activity", "label-1", "--sport-type", "100")
    assert captured_calls == [("getActivityDetail", {"labelId": "label-1", "sportType": 100})]


def test_analyze_passes_focus(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    _invoke("analyze", "label-1", "-s", "100", "--focus", "pace stability")
    assert captured_calls == [
        (
            "analyzeActivityDetail",
            {"labelId": "label-1", "sportType": 100, "focus": "pace stability"},
        )
    ]


def test_invalid_date_is_rejected(captured_calls: list[tuple[str, dict[str, Any]]]) -> None:
    result = _invoke("sleep", "--from", "not-a-date")
    assert result.exit_code != 0
    assert captured_calls == []


def test_json_flag_emits_raw_payload(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    result = _invoke("profile", "--json")
    assert result.exit_code == 0
    assert '"content"' in result.stdout
    assert '"isError": false' in result.stdout
