from __future__ import annotations

import json
import os
from pathlib import Path

from coros_cli.mcp.models import McpOAuthState


def _config_dir() -> Path:
    """Per-user config directory, honouring XDG_CONFIG_HOME."""
    base = os.environ.get("XDG_CONFIG_HOME")
    return Path(base) / "coros-cli" if base else Path.home() / ".config" / "coros-cli"


def mcp_oauth_path() -> Path:
    """Path of the MCP OAuth credential file."""
    return _config_dir() / "mcp-oauth.json"


def load_mcp_state() -> McpOAuthState | None:
    path = mcp_oauth_path()
    if not path.exists():
        return None
    try:
        return McpOAuthState.model_validate_json(path.read_text())
    except (json.JSONDecodeError, ValueError):
        return None


def save_mcp_state(state: McpOAuthState) -> None:
    path = mcp_oauth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(indent=2))
    path.chmod(0o600)


def clear_mcp_state() -> bool:
    """Delete the stored MCP OAuth credentials. Returns True if a file was removed."""
    path = mcp_oauth_path()
    if not path.exists():
        return False
    path.unlink()
    return True
