from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, timedelta
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from coros_cli.api.mobile import CorosApiError, fetch_sleep
from coros_cli.auth import CorosAuthError, ensure_user_id
from coros_cli.auth import login as auth_login
from coros_cli.cache import load_sleep_cache, merge_records, save_sleep_cache
from coros_cli.config import load_auth, save_auth
from coros_cli.mcp.commands import mcp_app
from coros_cli.models import Region, SleepRecord

_APP_HELP = """\
Coros sleep CLI — extract sleep metrics from your Coros Training Hub account.

Commands:
  login   Authenticate once, stores credentials under ~/.config/coros-cli/.
  sleep   Display sleep records from the local cache, refreshing on demand.
  mcp     Talk to the official COROS MCP server (experimental, read-only).

Data returned per night (all optional, may be null):
  - total / deep / light / rem / awake / nap (all in minutes)
  - avg_hr / min_hr / max_hr (overnight heart rate, bpm)
  - hrv_avg (overnight HRV, rmssd in ms — from the web /analyse API)

Key constraint: pulling fresh sleep data requires a Coros mobile-API login,
which disconnects the Coros app from your phone. The CLI caches results
locally (~/.config/coros-cli/data/sleep.json) to minimize this — one refresh
per week is enough for most use cases. See `coros sleep --help` for details.
"""

app = typer.Typer(help=_APP_HELP)
app.add_typer(mcp_app, name="mcp")
console = Console()
err_console = Console(stderr=True)


def _format_duration(minutes: int | None) -> str:
    if minutes is None:
        return "-"
    h, m = divmod(minutes, 60)
    return f"{h}h{m:02d}"


def _format_date(yyyymmdd: str) -> str:
    if len(yyyymmdd) != 8:
        return yyyymmdd
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"


def _parse_date(value: str) -> str:
    """Parse YYYY-MM-DD → YYYYMMDD, or pass through YYYYMMDD."""
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    raise typer.BadParameter(f"Invalid date: {value!r} (expected YYYY-MM-DD)")


def _render_sleep_table(records: list[SleepRecord]) -> Table:
    table = Table(title=f"Sleep ({len(records)} nights)")
    table.add_column("Date")
    table.add_column("Total", justify="right")
    table.add_column("Deep", justify="right")
    table.add_column("Light", justify="right")
    table.add_column("REM", justify="right")
    table.add_column("Awake", justify="right")
    table.add_column("Avg HR", justify="right")
    table.add_column("HRV", justify="right")
    for r in records:
        table.add_row(
            _format_date(r.date),
            _format_duration(r.total_minutes),
            _format_duration(r.phases.deep_minutes),
            _format_duration(r.phases.light_minutes),
            _format_duration(r.phases.rem_minutes),
            _format_duration(r.phases.awake_minutes),
            str(r.avg_hr) if r.avg_hr is not None else "-",
            str(r.hrv_avg) if r.hrv_avg is not None else "-",
        )
    return table


@app.command()
def login(
    email: Annotated[str, typer.Option(prompt=True)],
    password: Annotated[str, typer.Option(prompt=True, hide_input=True)],
    region: Annotated[Region, typer.Option(help="eu/us/asia/cn — auto-detected")] = "eu",
    with_mobile: Annotated[
        bool,
        typer.Option(
            "--with-mobile",
            help="Also log in to the mobile API now (will disconnect the Coros app on your phone).",
        ),
    ] = False,
) -> None:
    """Log in to Coros. Captures the web token + userId required for HRV.

    Credentials (pwd_hash, not plaintext) are stored in
    ~/.config/coros-cli/config.json (mode 0600). Run this once; the CLI
    self-heals missing fields on later sleep refreshes using the stored hash.

    --with-mobile forces the mobile-API login immediately, which disconnects
    the Coros app on your phone. Omit it to defer the kick until the first
    `coros sleep` refresh.
    """
    try:
        auth = asyncio.run(auth_login(email, password, region=region, with_mobile=with_mobile))
    except CorosAuthError as e:
        err_console.print(f"[red]Login failed:[/red] {e}")
        raise typer.Exit(1) from e
    save_auth(auth)
    mobile_note = "" if auth.mobile_access_token else " (mobile login deferred)"
    console.print(f"[green]Logged in[/green] — region: {auth.region}{mobile_note}")


_CACHE_TTL_DAYS = 7.0


def _confirm_kick(yes: bool) -> bool:
    if yes:
        return True
    err_console.print(
        "[yellow]Refreshing sleep data requires logging into the Coros mobile API,\n"
        "which will disconnect you from the Coros app on your phone.[/yellow]"
    )
    return typer.confirm("Proceed with refresh?", default=False)


@app.command()
def sleep(
    from_: Annotated[
        str | None,
        typer.Option("--from", help="Inclusive start date (YYYY-MM-DD or YYYYMMDD)."),
    ] = None,
    to: Annotated[
        str | None,
        typer.Option(
            "--to", help="Inclusive end date (YYYY-MM-DD or YYYYMMDD). Defaults to today."
        ),
    ] = None,
    days: Annotated[
        int,
        typer.Option(help="Last N days if --from/--to are omitted. Default 7."),
    ] = 7,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit records as JSON on stdout. See command help for schema."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Refresh from the API even if the cache is fresh."),
    ] = False,
    offline: Annotated[
        bool,
        typer.Option(
            "--offline",
            help="Never hit the network; exit 2 if a refresh would be needed.",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Skip the y/N prompt before refreshing (the refresh kicks the phone app).",
        ),
    ] = False,
) -> None:
    """Show sleep records. Reads from local cache; refreshes on demand.

    Default range is the last 7 days; override with --from/--to (YYYY-MM-DD)
    or --days N. Output is a Rich table unless --json is set.

    JSON output is a list of records with this schema:
      {
        "date": "YYYYMMDD",
        "total_minutes": int|null,
        "phases": {"deep_minutes": int|null, "light_minutes": int|null,
                    "rem_minutes": int|null, "awake_minutes": int|null,
                    "nap_minutes": int|null},
        "avg_hr": int|null, "min_hr": int|null, "max_hr": int|null,
        "hrv_avg": int|null   // rmssd ms, from web API
      }

    Cache behavior:
      - File: ~/.config/coros-cli/data/sleep.json
      - A refresh is triggered when: the cache is missing, older than 7 days,
        any day in the requested range is not cached, or --force is set.
      - A refresh logs into the Coros mobile API, which disconnects the
        Coros app on your phone. The CLI asks for confirmation unless --yes.
      - --offline forbids network access; exits 2 if a refresh would be
        needed. Useful for recurrent reads that must never kick the phone.

    Recommended agent workflow:
      Weekly sync:  coros sleep --days 14 --yes
      Daily reads:  coros sleep --offline --json   (fails loudly if stale)

    Exit codes: 0 ok, 1 API error / not logged in, 2 --offline but refresh
    needed.
    """
    auth = load_auth()
    if auth is None:
        err_console.print("[red]Not logged in.[/red] Run: coros login")
        raise typer.Exit(1)

    today = date.today()
    end = _parse_date(to) if to else today.strftime("%Y%m%d")
    start = _parse_date(from_) if from_ else (today - timedelta(days=days - 1)).strftime("%Y%m%d")

    cache = load_sleep_cache()
    needs_refresh = force or cache.is_stale(_CACHE_TTL_DAYS) or not cache.covers(start, end)

    if needs_refresh and offline:
        err_console.print(
            f"[red]Cache insufficient[/red] (stale={cache.is_stale(_CACHE_TTL_DAYS)}, "
            f"covers={cache.covers(start, end)}) and --offline set. Aborting."
        )
        raise typer.Exit(2)

    if needs_refresh:
        if not _confirm_kick(yes):
            err_console.print("[yellow]Refresh cancelled; showing what's in cache.[/yellow]")
        else:
            try:
                if not auth.user_id:
                    auth = asyncio.run(ensure_user_id(auth))
                    save_auth(auth)
                new_auth, fetched = asyncio.run(fetch_sleep(auth, start, end))
            except (CorosApiError, CorosAuthError) as e:
                err_console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(1) from e
            if new_auth != auth:
                save_auth(new_auth)
            cache = merge_records(cache, fetched)
            save_sleep_cache(cache)

    records = cache.in_range(start, end)

    if json_output:
        import json

        sys.stdout.write(json.dumps([r.model_dump() for r in records], indent=2, default=str))
        sys.stdout.write("\n")
    else:
        if not records:
            err_console.print("[yellow]No records in cache for the requested range.[/yellow]")
        console.print(_render_sleep_table(records))
        age = cache.age_days()
        if age != float("inf"):
            console.print(f"[dim]cache: {age:.1f}d old, {len(cache.records)} nights stored[/dim]")


if __name__ == "__main__":
    app()
