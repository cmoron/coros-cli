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


def test_sleep_passes_date_range(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    result = _invoke("sleep", "--days", "3", "--to", "2026-05-25")
    assert result.exit_code == 0
    tool, args = captured_calls[0]
    assert tool == "querySleepOverview"
    assert args["endDate"] == "20260525"
    assert args["startDate"] == "20260523"
    assert args["days"] == 3
    assert "timezone" not in args


def test_sleep_rejects_unsupported_timezone(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    result = _invoke("sleep", "--days", "1", "--tz", "Asia/Tokyo")
    assert result.exit_code != 0
    assert captured_calls == []


def test_hrv_passes_days(captured_calls: list[tuple[str, dict[str, Any]]]) -> None:
    _invoke("hrv", "--days", "7")
    assert captured_calls == [("querySleepHrv", {"days": 7})]


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


def test_analyze_explains_removed_tool(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    result = _invoke("analyze")
    assert result.exit_code != 0
    assert "COROS removed" in result.output
    assert captured_calls == []


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


def test_sleep_recent_days_uses_coros_timezone(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    result = _invoke("sleep", "--days", "3")
    assert result.exit_code == 0
    assert captured_calls == [("querySleepOverview", {"days": 3})]


@pytest.mark.parametrize("command", ["health", "hr", "resting", "stress", "schedule", "activities"])
def test_commands_do_not_send_timezone(
    command: str,
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    result = _invoke(command)
    assert result.exit_code == 0
    assert "timezone" not in captured_calls[0][1]


def test_hrv_rejects_more_than_seven_days(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    result = _invoke("hrv", "--days", "8")
    assert result.exit_code != 0
    assert captured_calls == []


@pytest.mark.parametrize("command", ["hr", "hrv"])
def test_health_commands_accept_explicit_dates(
    command: str,
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    result = _invoke(command, "--from", "2026-11-01", "--to", "2026-11-02")
    assert result.exit_code == 0, result.output
    assert captured_calls[0][1] == {
        "startDate": "20261101",
        "endDate": "20261102",
        "days": 7,
    }


def test_schedule_defaults_to_coros_current_week(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    assert _invoke("schedule").exit_code == 0
    assert captured_calls == [("queryTrainingSchedule", {})]


def test_laps_alias_passes_json_arguments(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    result = _invoke("laps", "--args", '{"labelId":"run-1","sportType":100}', "--json")
    assert result.exit_code == 0, result.output
    assert captured_calls == [("queryActivityLapData", {"labelId": "run-1", "sportType": 100})]
    assert '"content"' in result.stdout


@pytest.mark.parametrize("args", ["[]", "invalid"])
def test_laps_rejects_invalid_json(
    args: str,
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    result = _invoke("laps", "--args", args)
    assert result.exit_code != 0
    assert "JSON" in result.output
    assert captured_calls == []


@pytest.mark.parametrize("json_output", [False, True])
def test_tool_error_sets_failure_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    json_output: bool,
) -> None:
    monkeypatch.setattr(
        runner,
        "call_tool",
        lambda *_: {
            "isError": True,
            "content": [{"type": "text", "text": "server rejected request"}],
        },
    )
    result = _invoke("profile", *(["--json"] if json_output else []))
    assert result.exit_code == 1
    assert "server rejected request" in result.stdout


# Top-level schema snapshot from the live EU MCP tools/list, 2026-11-10.
READ_CASES = [
    ("profile", {}),
    ("devices", {}),
    ("sleep", {}),
    ("health", {}),
    ("hr", {}),
    ("resting", {}),
    ("hrv", {}),
    ("stress", {}),
    ("recovery", {}),
    ("load", {}),
    ("schedule", {}),
    ("fitness", {}),
    ("activities", {}),
    ("activity", {}),
    ("laps", {"labelId": "run-1", "sportType": 100}),
    (
        "laps-window",
        {
            "labelId": "run-1",
            "sportType": 100,
            "startTimestamp": 1794222000,
            "endTimestamp": 1794222300,
        },
    ),
    ("cycles", {}),
    ("health-check", {}),
    ("stress-series", {}),
    ("scheduled-workout", {"date": "20261110", "idInPlan": "session-1"}),
    ("plan", {"planId": "plan-1"}),
    ("plans", {}),
    ("workout", {"workoutId": "workout-1"}),
    ("workouts", {}),
    ("fit-files", {"labelId": "run-1", "sportType": 100}),
    ("fit-urls", {"labelId": "run-1", "sportType": 100}),
]


def test_all_read_tools_are_reachable_with_valid_arguments(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    import json
    from pathlib import Path

    schemas = json.loads((Path(__file__).parent / "fixtures/mcp-tools.json").read_text())
    types: dict[str, type | tuple[type, ...]] = {
        "integer": int,
        "string": str,
        "array": list,
        "number": (float, int),
        "object": dict,
    }
    for command, args in READ_CASES:
        flags = ["--args", json.dumps(args)] if args else []
        if command == "activity":
            flags = ["run-1", "-s", "100"]
        result = _invoke(command, *flags)
        assert result.exit_code == 0, result.output
        tool, arguments = captured_calls[-1]
        schema = schemas[tool]
        assert set(arguments) <= schema["properties"].keys(), tool
        assert set(schema["required"]) <= arguments.keys(), tool
        for key, value in arguments.items():
            expected_type = types[schema["properties"][key]]
            assert isinstance(value, expected_type), (tool, key, value)
    assert {tool for tool, _ in captured_calls} == {
        name for name, schema in schemas.items() if schema["readOnly"]
    }
