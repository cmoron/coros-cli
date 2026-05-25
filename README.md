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
uv run coros analyze <labelId> -s 100 --focus "pace stability"
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
- `--tz IANA` — timezone for date bucketing (defaults to system timezone)
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
| `coros analyze <id>` | Coach-style analysis of one activity |

### Activity filters

`coros activities` accepts a `--sport` group name (`run`, `bike`, `swim`,
`gym`, `ski`, `walk`, `row`, `climb`, `tri`, `all`), a numeric COROS sport
code (e.g. `100` for outdoor run), or a comma-separated list mixing both.

```sh
coros activities --sport run --min-km 5 --max-pace 5:30
coros activities --sport 100,bike --days 30 --limit 50
coros activities --from 2026-04-01 --to 2026-04-30 --location Marseille
```

`coros activity` and `coros analyze` both require the activity's `labelId` and
its `--sport-type` (visible in `coros activities` output). `--focus` on
`coros analyze` is a free-text hint sent to the server (e.g. `"pace stability"`,
`"heart rate"`, `"cadence"`).

## Escape hatch — raw MCP access

The `coros mcp` group exposes the underlying MCP server directly. Useful when
COROS ships a tool the CLI does not yet wrap.

```sh
coros mcp tools                       # list server tools
coros mcp tools --json                # full JSON schemas
coros mcp call queryUserInfo          # invoke a tool with no arguments
coros mcp call querySleepData \
  --args '{"days": 3, "timezone": "Europe/Paris",
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
