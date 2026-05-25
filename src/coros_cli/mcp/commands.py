from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated

import typer
from rich.table import Table

from coros_cli.mcp.client import McpClientError
from coros_cli.mcp.oauth import McpOAuthError
from coros_cli.mcp.runner import (
    call_tool,
    console,
    emit_json,
    err_console,
    load_state_or_exit,
    render_result,
)
from coros_cli.mcp.session import begin_authorization, complete_authorization, ensure_fresh, revoke
from coros_cli.mcp.store import clear_mcp_state, load_mcp_state, mcp_oauth_path, save_mcp_state
from coros_cli.models import Region

_MCP_HELP = """\
Low-level access to the COROS MCP server.

Top-level commands like `coros sleep`, `coros activities`, etc. use the same
MCP backend; this group exposes the raw building blocks for debugging and
forward-compatibility when COROS ships new tools the CLI does not yet wrap.

Commands:
  auth     OAuth authorization-code login against the COROS MCP server.
  status   Show stored MCP credentials and token expiry.
  tools    List the tools exposed by the MCP server.
  call     Invoke an MCP tool by name with arbitrary JSON arguments.
  revoke   Revoke the refresh token and delete the local credentials.
"""

mcp_app = typer.Typer(help=_MCP_HELP, no_args_is_help=True)


@mcp_app.command("auth")
def auth(
    region: Annotated[
        Region,
        typer.Option(help="MCP server region. Only 'eu' is published; others fall back to eu."),
    ] = "eu",
) -> None:
    """Authenticate with the COROS MCP server via the OAuth authorization-code flow.

    Performs dynamic client registration, then opens an authorization-code grant
    with PKCE: you approve the CLI in a browser, no password is handled by
    coros-cli. After approving, the browser is redirected to a local URL that
    will NOT load (coros-cli runs no server) — that is expected. Copy that URL
    from the address bar and paste it back here.
    """
    try:
        pending = asyncio.run(begin_authorization(region))
    except McpOAuthError as e:
        err_console.print(f"[red]MCP auth failed:[/red] {e}")
        raise typer.Exit(1) from e

    console.print("\n[bold]Authorize coros-cli with COROS:[/bold]")
    console.print("  1. Open this URL in your browser and approve access:")
    console.print()
    console.print(f"     [cyan]{pending.authorization_url}[/cyan]", soft_wrap=True)
    console.print()
    console.print(
        "  2. After approval the browser is redirected to "
        f"[dim]{pending.redirect_uri}[/dim] —\n"
        "     that page will fail to load ([dim]connection refused[/dim]). That is normal.\n"
        "  3. Copy the full URL from the browser address bar and paste it below\n"
        "     (or just the [bold]code[/bold] value from that URL).\n"
    )
    pasted = typer.prompt("Redirected URL or code").strip()

    try:
        state = asyncio.run(complete_authorization(pending, pasted))
    except McpOAuthError as e:
        err_console.print(f"[red]MCP auth failed:[/red] {e}")
        raise typer.Exit(1) from e
    save_mcp_state(state)
    console.print(f"[green]Authenticated[/green] with MCP server — region: {state.region}")


@mcp_app.command("status")
def status() -> None:
    """Show the stored MCP OAuth credentials and access-token freshness."""
    state = load_mcp_state()
    if state is None:
        console.print("[yellow]Not authenticated.[/yellow] Run: coros auth")
        raise typer.Exit(0)

    expired = state.access_expired()
    if state.expires_at_ms:
        delta_s = (state.expires_at_ms - time.time() * 1000) / 1000
        expiry = f"expired {-delta_s / 60:.0f}m ago" if delta_s < 0 else f"in {delta_s / 60:.0f}m"
    else:
        expiry = "unknown"

    table = Table(title="MCP OAuth status", show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Region", state.region)
    table.add_row("Issuer", state.issuer)
    table.add_row("Client ID", state.client_id)
    table.add_row("Scope", state.scope or "-")
    table.add_row("Access token", "present" if state.access_token else "missing")
    table.add_row("Refresh token", "present" if state.refresh_token else "missing")
    table.add_row(
        "Access token expiry",
        f"[red]{expiry}[/red]" if expired else f"[green]{expiry}[/green]",
    )
    table.add_row("File", str(mcp_oauth_path()))
    console.print(table)
    if expired and state.refresh_token:
        console.print("[dim]Token is stale; the next command will refresh it automatically.[/dim]")


@mcp_app.command("tools")
def tools(
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit the raw tool list as JSON on stdout.")
    ] = False,
) -> None:
    """List the tools exposed by the COROS MCP server."""
    state = load_state_or_exit()
    from coros_cli.mcp.session import build_client

    async def _list() -> list[dict[str, object]]:
        fresh = await ensure_fresh(state)
        client = build_client(fresh, save_mcp_state)
        async with client:
            return await client.list_tools()

    try:
        listed = asyncio.run(_list())
    except (McpClientError, McpOAuthError, RuntimeError) as e:
        err_console.print(f"[red]MCP error:[/red] {e}")
        raise typer.Exit(1) from e

    if json_output:
        emit_json(listed)
        return
    if not listed:
        console.print("[yellow]The MCP server exposes no tools.[/yellow]")
        return
    table = Table(title=f"MCP tools ({len(listed)})")
    table.add_column("Name", style="bold cyan")
    table.add_column("Description")
    for tool in listed:
        table.add_row(str(tool.get("name", "?")), str(tool.get("description", "")).strip())
    console.print(table)


@mcp_app.command("call")
def call(
    tool: Annotated[str, typer.Argument(help="Name of the MCP tool to invoke.")],
    args: Annotated[str, typer.Option("--args", help="Tool arguments as a JSON object.")] = "{}",
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit the raw tool result as JSON on stdout.")
    ] = False,
) -> None:
    """Invoke an MCP tool by name with JSON arguments."""
    try:
        arguments = json.loads(args)
    except json.JSONDecodeError as e:
        raise typer.BadParameter(f"--args is not valid JSON: {e}") from e
    if not isinstance(arguments, dict):
        raise typer.BadParameter("--args must be a JSON object")
    render_result(call_tool(tool, arguments), json_output=json_output)


@mcp_app.command("revoke")
def revoke_cmd() -> None:
    """Revoke the MCP refresh token and delete the local credentials."""
    state = load_mcp_state()
    if state is None:
        console.print("[yellow]Nothing to revoke.[/yellow]")
        return
    try:
        asyncio.run(revoke(state))
    except (McpOAuthError, McpClientError) as e:
        err_console.print(f"[yellow]Revocation request failed ({e}); clearing local file anyway.")
    clear_mcp_state()
    console.print("[green]Revoked[/green] — local MCP credentials removed.")
