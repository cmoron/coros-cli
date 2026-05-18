from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from coros_cli.mcp.client import McpClientError
from coros_cli.mcp.models import McpOAuthState
from coros_cli.mcp.oauth import McpOAuthError
from coros_cli.mcp.session import (
    begin_authorization,
    build_client,
    complete_authorization,
    ensure_fresh,
    revoke,
)
from coros_cli.mcp.store import clear_mcp_state, load_mcp_state, mcp_oauth_path, save_mcp_state
from coros_cli.models import Region

_MCP_HELP = """\
Talk to the official COROS MCP server (experimental, read-only).

This is a separate, OAuth-based backend from `coros login` / `coros sleep`.
It does NOT disconnect the Coros app on your phone. Credentials are stored in
~/.config/coros-cli/mcp-oauth.json (mode 0600), independent of the mobile login.

Commands:
  auth     OAuth authorization-code login against the COROS MCP server.
  status   Show stored MCP credentials and token expiry.
  tools    List the tools exposed by the MCP server.
  call     Invoke an MCP tool by name.
  revoke   Revoke the refresh token and delete the local credentials.

`coros sleep` still uses the legacy mobile API; the MCP backend will replace
it once the COROS tool schema is known.
"""

mcp_app = typer.Typer(help=_MCP_HELP, no_args_is_help=True)
console = Console()
err_console = Console(stderr=True)


def _load_state_or_exit() -> McpOAuthState:
    state = load_mcp_state()
    if state is None:
        err_console.print("[red]Not authenticated with the MCP server.[/red] Run: coros mcp auth")
        raise typer.Exit(1)
    return state


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
    console.print("  1. Open this URL in your browser and approve access:\n")
    console.print(f"     [cyan]{pending.authorization_url}[/cyan]\n")
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
        console.print("[yellow]Not authenticated.[/yellow] Run: coros mcp auth")
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


def _emit_json(payload: Any) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, default=str))
    sys.stdout.write("\n")


@mcp_app.command("tools")
def tools(
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit the raw tool list as JSON on stdout.")
    ] = False,
) -> None:
    """List the tools exposed by the COROS MCP server."""
    state = _load_state_or_exit()
    try:
        listed = asyncio.run(_list_tools(state))
    except (McpClientError, McpOAuthError, RuntimeError) as e:
        err_console.print(f"[red]MCP error:[/red] {e}")
        raise typer.Exit(1) from e

    if json_output:
        _emit_json(listed)
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
    state = _load_state_or_exit()
    try:
        arguments = json.loads(args)
    except json.JSONDecodeError as e:
        raise typer.BadParameter(f"--args is not valid JSON: {e}") from e
    if not isinstance(arguments, dict):
        raise typer.BadParameter("--args must be a JSON object")

    try:
        result = asyncio.run(_call_tool(state, tool, arguments))
    except (McpClientError, McpOAuthError, RuntimeError) as e:
        err_console.print(f"[red]MCP error:[/red] {e}")
        raise typer.Exit(1) from e

    if json_output:
        _emit_json(result)
        return
    _render_tool_result(result)


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


async def _list_tools(state: McpOAuthState) -> list[dict[str, Any]]:
    state = await ensure_fresh(state)
    client = build_client(state, save_mcp_state)
    async with client:
        return await client.list_tools()


async def _call_tool(state: McpOAuthState, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    state = await ensure_fresh(state)
    client = build_client(state, save_mcp_state)
    async with client:
        return await client.call_tool(tool, arguments)


def _render_tool_result(result: dict[str, Any]) -> None:
    if result.get("isError"):
        err_console.print("[red]Tool reported an error.[/red]")
    content = result.get("content")
    if not isinstance(content, list) or not content:
        _emit_json(result)
        return
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            console.print(block.get("text", ""))
        else:
            _emit_json(block)
