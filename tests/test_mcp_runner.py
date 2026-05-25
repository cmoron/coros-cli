from __future__ import annotations

from io import StringIO
from typing import Any

import pytest
from rich.console import Console

from coros_cli.mcp import runner
from coros_cli.mcp.runner import _unwrap_text, default_timezone, emit_json, render_result


class _CaptureConsole:
    """Bind runner's stdout/stderr Rich consoles to capturable StringIOs."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.out = StringIO()
        self.err = StringIO()
        monkeypatch.setattr(runner, "console", Console(file=self.out, width=120))
        monkeypatch.setattr(runner, "err_console", Console(file=self.err, width=120))


def test_default_timezone_uses_tz_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    assert default_timezone() == "Asia/Tokyo"


def test_default_timezone_strips_leading_colon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", ":Europe/Paris")
    assert default_timezone() == "Europe/Paris"


def test_default_timezone_falls_back_to_utc(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.delenv("TZ", raising=False)
    # Reroute the symlink/file lookups through a non-existing path.
    monkeypatch.setattr("os.readlink", lambda _p: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr("builtins.open", lambda *_a, **_k: (_ for _ in ()).throw(OSError()))
    assert default_timezone() == "UTC"


def test_unwrap_text_decodes_double_encoded_string() -> None:
    payload = '"Hello\\nworld"'
    assert _unwrap_text(payload) == "Hello\nworld"


def test_unwrap_text_keeps_plain_text() -> None:
    assert _unwrap_text("Plain text") == "Plain text"


def test_unwrap_text_keeps_non_string_json() -> None:
    # JSON objects/arrays should not be flattened to a string.
    assert _unwrap_text('{"a": 1}') == '{"a": 1}'
    assert _unwrap_text("[1, 2]") == "[1, 2]"


def test_emit_json_writes_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    emit_json({"a": 1})
    out = capsys.readouterr().out
    assert '"a": 1' in out
    assert out.endswith("\n")


def test_render_result_prints_text_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _CaptureConsole(monkeypatch)
    render_result(
        {"content": [{"type": "text", "text": '"Hello\\nworld"'}], "isError": False},
        json_output=False,
    )
    assert "Hello" in cap.out.getvalue()
    assert "world" in cap.out.getvalue()


def test_render_result_emits_full_json_when_requested(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _CaptureConsole(monkeypatch)
    result = {"content": [{"type": "text", "text": "hi"}], "isError": False}
    render_result(result, json_output=True)
    out = capsys.readouterr().out
    assert '"isError": false' in out


def test_render_result_flags_error(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _CaptureConsole(monkeypatch)
    render_result(
        {"content": [{"type": "text", "text": "boom"}], "isError": True},
        json_output=False,
    )
    assert "error" in cap.err.getvalue().lower()


def test_render_result_falls_back_to_json_for_unknown_block(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _CaptureConsole(monkeypatch)
    render_result(
        {"content": [{"type": "image", "data": "..."}], "isError": False},
        json_output=False,
    )
    assert '"type": "image"' in capsys.readouterr().out
