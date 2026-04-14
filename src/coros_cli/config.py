from __future__ import annotations

import os
from pathlib import Path

from coros_cli.models import StoredAuth


def config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "coros-cli"


def config_path() -> Path:
    return config_dir() / "config.json"


def load_auth() -> StoredAuth | None:
    path = config_path()
    if not path.exists():
        return None
    return StoredAuth.model_validate_json(path.read_text())


def save_auth(auth: StoredAuth) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(auth.model_dump_json(indent=2))
    path.chmod(0o600)
