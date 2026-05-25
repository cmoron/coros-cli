from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated

import typer

from coros_cli.mcp.commands import auth as mcp_auth
from coros_cli.mcp.commands import mcp_app
from coros_cli.mcp.commands import revoke_cmd as mcp_revoke
from coros_cli.mcp.runner import default_timezone, run

_APP_HELP = """\
COROS CLI — talk to the official COROS MCP backend.

Run `coros auth` once (OAuth in your browser, no password handled by the CLI),
then any of the data commands below. Credentials live in
~/.config/coros-cli/mcp-oauth.json (mode 0600).

Most commands accept `--days N`, `--from YYYY-MM-DD`, `--to YYYY-MM-DD`,
`--tz <IANA>` and `--json`. Run `coros <command> --help` for details.
"""

app = typer.Typer(help=_APP_HELP, no_args_is_help=True)
app.add_typer(mcp_app, name="mcp")


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> str:
    """Parse YYYY-MM-DD or YYYYMMDD into the YYYYMMDD form COROS expects."""
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    raise typer.BadParameter(f"Invalid date: {value!r} (expected YYYY-MM-DD)")


def _date_range(from_: str | None, to: str | None, days: int) -> tuple[str, str]:
    """Resolve a (startDate, endDate) pair in YYYYMMDD form from CLI flags."""
    end = _parse_date(to) if to else date.today().strftime("%Y%m%d")
    if from_:
        start = _parse_date(from_)
    else:
        start_dt = datetime.strptime(end, "%Y%m%d").date() - timedelta(days=days - 1)
        start = start_dt.strftime("%Y%m%d")
    return start, end


def _tz(tz: str | None) -> str:
    return tz or default_timezone()


# ---------------------------------------------------------------------------
# Auth aliases — `coros auth` / `coros logout` shortcut to the MCP commands
# ---------------------------------------------------------------------------


app.command("auth")(mcp_auth)
app.command("logout")(mcp_revoke)


# ---------------------------------------------------------------------------
# Profile & devices
# ---------------------------------------------------------------------------


@app.command()
def profile(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show your COROS profile (height, weight, birthday, gender)."""
    run("queryUserInfo", {}, json_output=json_output)


@app.command()
def devices(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List the COROS devices bound to your account."""
    run("queryDevices", {}, json_output=json_output)


# ---------------------------------------------------------------------------
# Daily health metrics
# ---------------------------------------------------------------------------


_DAYS = Annotated[int, typer.Option(help="Number of recent days to query.")]
_FROM = Annotated[str | None, typer.Option("--from", help="Start date YYYY-MM-DD or YYYYMMDD.")]
_TO = Annotated[str | None, typer.Option("--to", help="End date YYYY-MM-DD or YYYYMMDD.")]
_TZ = Annotated[str | None, typer.Option("--tz", help="IANA timezone (defaults to system).")]
_JSON = Annotated[bool, typer.Option("--json", help="Emit the raw tool result as JSON.")]


@app.command()
def sleep(
    days: _DAYS = 7,
    from_: _FROM = None,
    to: _TO = None,
    tz: _TZ = None,
    json_output: _JSON = False,
) -> None:
    """Sleep score, duration, deep/light/REM ratios, awake count, naps."""
    start, end = _date_range(from_, to, days)
    run(
        "querySleepData",
        {"startDate": start, "endDate": end, "days": days, "timezone": _tz(tz)},
        json_output=json_output,
    )


@app.command()
def health(
    days: _DAYS = 7,
    tz: _TZ = None,
    json_output: _JSON = False,
) -> None:
    """Daily wellness summary: steps, calories, HR, stress, sleep."""
    run(
        "queryDailyHealthData",
        {"days": days, "timezone": _tz(tz)},
        json_output=json_output,
    )


@app.command()
def hr(
    days: _DAYS = 7,
    tz: _TZ = None,
    json_output: _JSON = False,
) -> None:
    """Daily average heart rate."""
    run(
        "queryAvgHeartRate",
        {"days": days, "timezone": _tz(tz)},
        json_output=json_output,
    )


@app.command()
def resting(
    days: _DAYS = 7,
    tz: _TZ = None,
    json_output: _JSON = False,
) -> None:
    """Daily resting heart rate."""
    run(
        "queryRestingHeartRate",
        {"days": days, "timezone": _tz(tz)},
        json_output=json_output,
    )


@app.command()
def hrv(
    days: _DAYS = 7,
    tz: _TZ = None,
    json_output: _JSON = False,
) -> None:
    """Daily HRV assessment (average, normal range, evaluation)."""
    run(
        "queryHrvAssessment",
        {"days": days, "timezone": _tz(tz)},
        json_output=json_output,
    )


@app.command()
def stress(
    days: _DAYS = 7,
    tz: _TZ = None,
    json_output: _JSON = False,
) -> None:
    """Daily average stress level."""
    run(
        "queryStressLevel",
        {"days": days, "timezone": _tz(tz)},
        json_output=json_output,
    )


@app.command()
def recovery(
    json_output: _JSON = False,
) -> None:
    """Current recovery status (percentage, level, time-to-full)."""
    run("queryRecoveryStatus", {}, json_output=json_output)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


@app.command()
def load(
    days: _DAYS = 7,
    json_output: _JSON = False,
) -> None:
    """Training load assessment (short/long-term load, ratio, comments)."""
    run(
        "queryTrainingLoadAssessment",
        {"days": days},
        json_output=json_output,
    )


@app.command()
def schedule(
    from_: _FROM = None,
    to: _TO = None,
    days: _DAYS = 7,
    tz: _TZ = None,
    json_output: _JSON = False,
) -> None:
    """Training schedule for the requested date range (defaults to this week)."""
    start, end = _date_range(from_, to, days)
    run(
        "queryTrainingSchedule",
        {"startDate": start, "endDate": end, "timezone": _tz(tz)},
        json_output=json_output,
    )


@app.command()
def fitness(
    json_output: _JSON = False,
) -> None:
    """Fitness overview: VO2max, running level, threshold pace, race predictions."""
    run("queryFitnessAssessmentOverview", {}, json_output=json_output)


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------


_SPORT_GROUPS: dict[str, list[int]] = {
    "run": [100, 101, 102, 103, 104, 105, 106],
    "bike": [200, 201, 202, 203, 204, 205, 299],
    "swim": [300, 301],
    "gym": [400, 401, 402],
    "ski": [500, 501, 502, 503],
    "walk": [900],
    "row": [700, 701, 702, 704, 705],
    "climb": [800, 801, 802],
    "tri": [10000],
    "all": [65535],
}


def _resolve_sport_codes(sport: str | None) -> list[int]:
    if not sport:
        return [65535]
    if sport in _SPORT_GROUPS:
        return _SPORT_GROUPS[sport]
    codes: list[int] = []
    for token in sport.split(","):
        token = token.strip()
        if not token:
            continue
        if token in _SPORT_GROUPS:
            codes.extend(_SPORT_GROUPS[token])
            continue
        try:
            codes.append(int(token))
        except ValueError as e:
            raise typer.BadParameter(
                f"--sport: unknown sport {token!r}. "
                f"Known groups: {', '.join(sorted(_SPORT_GROUPS))}, or pass a numeric code."
            ) from e
    return codes or [65535]


@app.command()
def activities(
    days: _DAYS = 7,
    from_: _FROM = None,
    to: _TO = None,
    sport: Annotated[
        str | None,
        typer.Option(
            "--sport",
            help=(
                "Sport filter. Group name (run, bike, swim, gym, ski, walk, row, "
                "climb, tri, all), numeric code, or comma-separated list."
            ),
        ),
    ] = None,
    min_km: Annotated[
        float | None, typer.Option("--min-km", help="Minimum distance in km.")
    ] = None,
    max_km: Annotated[
        float | None, typer.Option("--max-km", help="Maximum distance in km.")
    ] = None,
    min_min: Annotated[
        int | None, typer.Option("--min-min", help="Minimum duration in minutes.")
    ] = None,
    max_min: Annotated[
        int | None, typer.Option("--max-min", help="Maximum duration in minutes.")
    ] = None,
    max_pace: Annotated[
        str | None, typer.Option("--max-pace", help="Maximum average pace e.g. 5:30.")
    ] = None,
    location: Annotated[
        str | None, typer.Option("--location", help="Location keyword (city, park…).")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max records to return.")] = 20,
    tz: _TZ = None,
    json_output: _JSON = False,
) -> None:
    """List workouts with optional date / sport / distance / duration filters."""
    start, end = _date_range(from_, to, days)
    args: dict[str, object] = {
        "startDate": start,
        "endDate": end,
        "sportTypeCodes": _resolve_sport_codes(sport),
        "minDistanceKm": min_km,
        "maxDistanceKm": max_km,
        "minDurationMinutes": min_min,
        "maxDurationMinutes": max_min,
        "maxAveragePace": max_pace,
        "locationKeyword": location,
        "limit": limit,
        "timezone": _tz(tz),
    }
    run("querySportRecords", args, json_output=json_output)


@app.command()
def activity(
    label_id: Annotated[str, typer.Argument(help="The activity labelId.")],
    sport_type: Annotated[
        int,
        typer.Option(
            "--sport-type",
            "-s",
            help="COROS sport type code (e.g. 100=outdoor run, 200=outdoor bike).",
        ),
    ],
    json_output: _JSON = False,
) -> None:
    """Detailed metrics for one activity (HR, pace, elevation, cadence…)."""
    run(
        "getActivityDetail",
        {"labelId": label_id, "sportType": sport_type},
        json_output=json_output,
    )


@app.command()
def analyze(
    label_id: Annotated[str, typer.Argument(help="The activity labelId.")],
    sport_type: Annotated[
        int,
        typer.Option(
            "--sport-type",
            "-s",
            help="COROS sport type code (e.g. 100=outdoor run, 200=outdoor bike).",
        ),
    ],
    focus: Annotated[
        str | None,
        typer.Option(
            "--focus",
            help="Optional analysis focus, e.g. 'pace stability', 'heart rate'.",
        ),
    ] = None,
    json_output: _JSON = False,
) -> None:
    """Coach-style analysis of an activity in plain language."""
    run(
        "analyzeActivityDetail",
        {"labelId": label_id, "sportType": sport_type, "focus": focus or ""},
        json_output=json_output,
    )


if __name__ == "__main__":
    app()
