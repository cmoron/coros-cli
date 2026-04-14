from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, timedelta
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from coros_cli.api.mobile import CorosApiError, fetch_sleep
from coros_cli.auth import CorosAuthError
from coros_cli.auth import login as auth_login
from coros_cli.config import load_auth, save_auth
from coros_cli.models import Region, SleepRecord

app = typer.Typer(help="CLI pour extraire vos données Coros (sommeil, activités).")
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
    for r in records:
        table.add_row(
            _format_date(r.date),
            _format_duration(r.total_minutes),
            _format_duration(r.phases.deep_minutes),
            _format_duration(r.phases.light_minutes),
            _format_duration(r.phases.rem_minutes),
            _format_duration(r.phases.awake_minutes),
            str(r.avg_hr) if r.avg_hr is not None else "-",
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
    """Authentifie vers Coros (web). L'API mobile est utilisée à la demande pour le sommeil."""
    try:
        auth = asyncio.run(auth_login(email, password, region=region, with_mobile=with_mobile))
    except CorosAuthError as e:
        err_console.print(f"[red]Login failed:[/red] {e}")
        raise typer.Exit(1) from e
    save_auth(auth)
    mobile_note = "" if auth.mobile_access_token else " (mobile login deferred)"
    console.print(f"[green]Logged in[/green] — region: {auth.region}{mobile_note}")


@app.command()
def sleep(
    from_: Annotated[str | None, typer.Option("--from", help="Start date YYYY-MM-DD")] = None,
    to: Annotated[str | None, typer.Option("--to", help="End date YYYY-MM-DD")] = None,
    days: Annotated[int, typer.Option(help="Last N days if --from/--to omitted")] = 7,
    json_output: Annotated[bool, typer.Option("--json", help="Raw JSON output")] = False,
) -> None:
    """Récupère les données de sommeil sur une plage de dates."""
    auth = load_auth()
    if auth is None:
        err_console.print("[red]Not logged in.[/red] Run: coros login")
        raise typer.Exit(1)

    if auth.mobile_access_token is None:
        err_console.print(
            "[yellow]First sleep fetch: logging into the Coros mobile API. "
            "This will disconnect you from the Coros app on your phone.[/yellow]"
        )

    today = date.today()
    end = _parse_date(to) if to else today.strftime("%Y%m%d")
    start = _parse_date(from_) if from_ else (today - timedelta(days=days - 1)).strftime("%Y%m%d")

    try:
        new_auth, records = asyncio.run(fetch_sleep(auth, start, end))
    except (CorosApiError, CorosAuthError) as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    if new_auth != auth:
        save_auth(new_auth)

    if json_output:
        import json

        sys.stdout.write(json.dumps([r.model_dump() for r in records], indent=2, default=str))
        sys.stdout.write("\n")
    else:
        console.print(_render_sleep_table(records))


if __name__ == "__main__":
    app()
