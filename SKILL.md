---
name: coros-data
description: Query COROS watch data with the coros CLI — sleep, HRV, heart rate, stress, recovery, training load, fitness, activities, laps, menstrual cycles, workouts and training plans. Use for COROS physiology or training questions, not other wearables.
---

# coros-data

Use the CLI to read the user's COROS account through the official MCP server.
Check `coros mcp status` first. If unauthenticated, ask the user to run
`coros auth` themselves: browser approval is required. Never run authentication
on their behalf.

Default output is server-provided text. `--json` emits the raw MCP result.
A nonzero exit code indicates failure, including a tool-level MCP error.

## Common commands

```sh
coros profile
coros devices
coros sleep --days 7
coros health --days 7
coros hr --days 7
coros resting --days 7
coros hrv --days 7
coros stress --days 7
coros recovery
coros load --days 7
coros fitness
coros schedule
coros activities --sport run --days 14 --limit 5
coros activity ACTIVITY_ID -s 100
```

Dates use the COROS account timezone. `--tz` is unsupported. Sleep and HRV
belong to the **wake-up date**: last night's sleep means today's date.
`sleep`, `hr`, `hrv`, `activities` and `schedule` accept `--from` / `--to`
in YYYY-MM-DD or YYYYMMDD format. HRV supports at most 7 recent days.
`schedule` defaults to the current Monday–Sunday week; `--days N` requests
recent days explicitly.

Activities accept `--sport` groups (`run`, `bike`, `swim`, `gym`, `ski`,
`walk`, `row`, `climb`, `tri`, `all`), numeric COROS codes, or comma-separated
combinations. Other filters: `--min-km`, `--max-km`, `--min-min`, `--max-min`,
`--max-pace 5:30`, `--location`, `--limit`. Reuse the returned `labelId` and
`sportType` for activity details and laps. For additional sports, inspect
the `querySportRecords` description in `coros mcp tools --json`.

## Structured commands

These commands accept `--args` as a JSON object with exact MCP field names,
plus `--json`. Inspect complete schemas and field descriptions using
`coros mcp tools --json`; do not invent fields or units.

| CLI | MCP tool |
|---|---|
| `laps` | `queryActivityLapData` |
| `laps-window` | `queryCustomActivityLapData` |
| `cycles` | `queryMenstruationCycles` |
| `health-check` | `queryHealthCheckTimeSeries` |
| `stress-series` | `queryStressTimeSeries` |
| `scheduled-workout` | `queryScheduledWorkoutDetails` |
| `plan` / `plans` | `queryTrainingPlanDetails` / `queryTrainingPlanLibrary` |
| `workout` / `workouts` | `queryWorkoutDetails` / `queryWorkoutLibrary` |
| `fit-files` / `fit-urls` | `downloadActivityFitFiles` / `queryActivityFitFileDownloadUrls` |

```sh
coros laps --args '{"labelId":"ACTIVITY_ID","sportType":100}'
coros stress-series --args '{"days":1}'
coros health-check --args '{"days":7}'
coros cycles --args '{"startDay":20261101,"endDay":20261130}'
coros plans
coros plan --args '{"planId":"PLAN_ID"}'
coros workouts
coros workout --args '{"workoutId":"WORKOUT_ID"}'
coros scheduled-workout --args '{"date":"20261110","idInPlan":"SESSION_ID"}'
coros fit-urls --args '{"labelId":"ACTIVITY_ID","sportType":100,"limit":1}'
```

For exact activity windows, get `startTimestamp` / `endTimestamp` from
activity records first, then pass Unix **seconds** to `laps-window` along
with `labelId` and `sportType`.

`health-check` and `stress-series` allow at most 7 recent days; explicit
`startDate` / `endDate` strings use YYYYMMDD. `cycles` uses integer
`startDay` / `endDay`. Empty results can be legitimate; do not invent data.

`fit-files --json` emits MCP binary resources without writing files to disk.
`fit-urls` provides download URLs. Both consume COROS's daily FIT quota;
request only the necessary files, maximum 10 per request.

## Analysis and raw MCP access

COROS removed `analyzeActivityDetail`. Retrieve activity details and laps,
then provide your own analysis based on those measurements.

```sh
coros mcp tools --json
coros mcp call TOOL_NAME --args '{"key":"value"}' --json
```

The raw interface can also call MCP write tools. Only invoke a write tool
when the user explicitly requests that account change. Reading data does
not authorize creating workouts, modifying plans, scheduling or uploading.
