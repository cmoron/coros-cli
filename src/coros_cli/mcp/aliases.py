"""Named CLI entry points for MCP tools with structured JSON inputs."""

from typing import Annotated

import typer

from coros_cli.mcp.commands import call

# Keep the MCP argument names and nested structures intact.
READ_COMMANDS = {
    "laps": "queryActivityLapData",
    "laps-window": "queryCustomActivityLapData",
    "cycles": "queryMenstruationCycles",
    "health-check": "queryHealthCheckTimeSeries",
    "stress-series": "queryStressTimeSeries",
    "scheduled-workout": "queryScheduledWorkoutDetails",
    "plan": "queryTrainingPlanDetails",
    "plans": "queryTrainingPlanLibrary",
    "workout": "queryWorkoutDetails",
    "workouts": "queryWorkoutLibrary",
    "fit-files": "downloadActivityFitFiles",
    "fit-urls": "queryActivityFitFileDownloadUrls",
}


def register_commands(app: typer.Typer) -> None:
    for name, tool in READ_COMMANDS.items():
        _register(app, name, tool)


def _register(app: typer.Typer, name: str, tool: str) -> None:
    def invoke(
        args: Annotated[str, typer.Option(help="MCP arguments as a JSON object.")] = "{}",
        json_output: Annotated[bool, typer.Option("--json", help="Emit the raw result.")] = False,
    ) -> None:
        call(tool, args, json_output)

    app.command(name, help=f"{tool}. Inspect its arguments with `coros mcp tools --json`.")(invoke)
