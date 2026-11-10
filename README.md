# coros-cli

Unofficial Python CLI on top of the official [COROS MCP server](https://mcpeu.coros.com).

Read-only access to sleep, HRV, heart rate, stress, recovery, training load, and
activities — using OAuth 2.0. No password is handled by the CLI; authentication
happens in your browser. Not affiliated with COROS.

Primarily designed for **AI agents**: every command produces structured text
(or `--json` raw output) suitable for piping into an LLM. See [`SKILL.md`](./SKILL.md)
for a ready-to-use agent skill bundle.

## Setup

```sh
uv sync
uv run coros --help
```

## Quick start

```sh
uv run coros auth                 # OAuth in your browser, runs once
uv run coros profile              # height, weight, birthday, gender
uv run coros sleep --days 7       # last 7 nights
uv run coros activities --sport run --days 14
uv run coros activity <labelId> -s 100
```

## Authentication

`coros auth` runs the OAuth 2.0 authorization-code flow with PKCE against the
COROS MCP server. It registers a public client dynamically (RFC 7591), opens
an authorization URL in the terminal, and asks you to paste back the redirect
URL after you approve in the browser.

Credentials (access + refresh token) live in `~/.config/coros-cli/mcp-oauth.json`
(mode `0600`). The CLI refreshes access tokens automatically when they expire.

```sh
coros auth                        # log in
coros mcp status                  # show token state and expiry
coros logout                      # revoke + delete local credentials
```

## Commands

All data commands share these flags where they make sense:

- `--days N` — number of recent days to query (default 7)
- `--from YYYY-MM-DD` / `--to YYYY-MM-DD` — explicit date range
Dates use the timezone configured in your COROS account; `--tz` is no longer supported.
Sleep dates refer to the wake-up day. HRV queries support at most 7 recent days.
- `--json` — emit the raw MCP tool result as JSON on stdout

| Command | What it returns |
|---|---|
| `coros profile` | Height, weight, birthday, age, gender |
| `coros devices` | Bound COROS devices and firmware info |
| `coros sleep` | Sleep score, duration, deep/light/REM ratios, awake count, naps |
| `coros health` | Daily wellness: steps, calories, HR, stress, sleep |
| `coros hr` | Daily average heart rate |
| `coros resting` | Daily resting heart rate |
| `coros hrv` | HRV average, normal range, evaluation per day |
| `coros stress` | Daily average stress level |
| `coros recovery` | Current recovery %, level, estimated full-recovery time |
| `coros load` | Training load (short/long-term, ratio, daily comments) |
| `coros schedule` | Training schedule for a date range |
| `coros fitness` | VO2max, running level, threshold pace, race predictions |
| `coros activities` | Workouts with filters (date, sport, distance, duration…) |
| `coros activity <id>` | Detailed metrics for one activity |
| `coros laps` / `coros laps-window` | Recorded laps / metrics over a timestamp window |
| `coros cycles` | Menstrual cycle data |
| `coros health-check` / `coros stress-series` | Detailed health / stress time series |
| `coros plans` / `coros plan` | Training plan library / details |
| `coros workouts` / `coros workout` | Workout library / details |
| `coros scheduled-workout` | Details of a scheduled session |
| `coros fit-files` / `coros fit-urls` | FIT resources / download URLs |

### Activity filters

`coros activities` accepts a `--sport` group name (`run`, `bike`, `swim`,
`gym`, `ski`, `walk`, `row`, `climb`, `tri`, `all`), a numeric COROS sport
code (e.g. `100` for outdoor run), or a comma-separated list mixing both.

```sh
coros activities --sport run --min-km 5 --max-pace 5:30
coros activities --sport 100,bike --days 30 --limit 50
coros activities --from 2026-04-01 --to 2026-04-30 --location Marseille
```

`coros activity` requires the activity's `labelId` and `--sport-type`
(visible in `coros activities` output). `coros analyze` has been removed by
COROS and exits with a migration hint; retrieve the activity metrics instead.

`hr` and `hrv` also accept `--from` / `--to`. Without dates, COROS resolves
recent days in your account timezone. `schedule` without flags returns the
current Monday–Sunday week; `--days N` explicitly requests the recent N days.

### Structured MCP arguments

The new commands in the table above accept `--args` as a JSON object, using
exact MCP field names, plus `--json` for raw output. The server validates
nested input structures. Inspect complete schemas and descriptions with
`coros mcp tools --json`.

```sh
coros laps --args '{"labelId":"ACTIVITY_ID","sportType":100}'
coros laps-window --args '{"labelId":"ACTIVITY_ID","sportType":100,"startTimestamp":1794222000,"endTimestamp":1794222300}'
coros health-check --args '{"days":7}'
coros stress-series --args '{"days":1}'
coros cycles --args '{"startDay":20261101,"endDay":20261130}'
coros plans
coros plan --args '{"planId":"PLAN_ID"}'
coros workouts
coros workout --args '{"workoutId":"WORKOUT_ID"}'
coros scheduled-workout --args '{"date":"20261110","idInPlan":"SESSION_ID"}'
coros fit-urls --args '{"labelId":"ACTIVITY_ID","sportType":100,"limit":1}'
```

`health-check` and `stress-series` support at most 7 recent days, as does
`hrv`; explicit dates can be passed using `startDate` / `endDate`.
`fit-files --json` emits the MCP result including binary resources; it does
not save `.fit` files to disk. `fit-urls` returns download links. Both count
against COROS's daily FIT quota (at most 10 files per request).

## Escape hatch — raw MCP access

The `coros mcp` group exposes the underlying MCP server directly. Useful when
COROS ships a tool the CLI does not yet wrap.

```sh
coros mcp tools                       # list server tools
coros mcp tools --json                # full JSON schemas
coros mcp call queryUserInfo          # invoke a tool with no arguments
coros mcp call querySleepOverview \
  --args '{"days": 3,
           "startDate": "20260523", "endDate": "20260525"}'
```

## Development

```sh
uv run pytest                # run the test suite
uv run ruff check src/ tests/
uv run mypy src/ tests/
```

Tests don't touch the network: the OAuth + MCP transport are unit-tested with
mocked HTTP, and the CLI tests stub out `runner.call_tool`.

COROS no longer exposes `analyzeActivityDetail`; `coros analyze` is currently unavailable.
Use `coros activity <id> -s <code>` to retrieve the metrics for your own analysis.
