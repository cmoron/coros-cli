---
name: coros-data
description: Query the user's COROS training watch data — sleep, HRV, resting / average heart rate, stress, recovery, daily health, training load, fitness assessment, workout history, and per-activity details. Trigger when the user asks about how they slept, their HRV / heart rate / stress trend, their recovery status, their fitness or VO2max, their training load, what they should train this week, recent workouts ("my last run", "this month's bike rides"), or wants a coach-style analysis of one activity. Do NOT trigger for non-COROS wearables (Garmin, Whoop, Oura, Apple Watch).
---

# coros-data

Read-only access to the user's COROS account through the `coros` CLI, which
wraps the official COROS MCP server (OAuth 2.0). No password is handled —
authentication is browser-based and persisted in `~/.config/coros-cli/`.

The CLI is the right tool for any factual question about the user's
**physiology, sleep, recovery, training load, or workout history** as recorded
by their COROS watch. It is **not** suited for live device control, route
planning, or modifying training plans (read-only API).

## Prerequisites

Check that the user is authenticated before running data commands:

```bash
coros mcp status
```

If the output reports `Not authenticated.`, tell the user to run `coros auth`
themselves — the OAuth flow opens a URL in their browser and requires their
manual approval. **Never run `coros auth` on the user's behalf.**

## Output format

By default every command prints human-formatted text on stdout (COROS shapes the
text — you can return it nearly verbatim). Add `--json` to any command to get
the raw MCP tool result for parsing.

```bash
coros sleep --days 3            # text, paste-friendly
coros sleep --days 3 --json     # raw JSON, parse-friendly
```

## Command catalog

All time-series commands accept `--days N` (default 7), `--from YYYY-MM-DD`,
`--to YYYY-MM-DD`, `--tz <IANA>` (defaults to the host timezone), and `--json`.

| Command | What it answers |
|---|---|
| `coros profile` | Height, weight, age, gender |
| `coros devices` | Bound watches / sensors |
| `coros sleep` | Sleep score, total duration, deep/light/REM ratios, awake count, naps |
| `coros health` | Daily wellness summary (steps, calories, HR, stress, sleep) |
| `coros hr` | Daily average heart rate |
| `coros resting` | Daily resting heart rate |
| `coros hrv` | Daily HRV (avg, normal range, evaluation) |
| `coros stress` | Daily average stress level |
| `coros recovery` | Current recovery % + estimated time to full recovery |
| `coros load` | Short/long-term training load + ratio + daily comments |
| `coros schedule` | Scheduled workouts for a date range |
| `coros fitness` | VO2max, running level, threshold pace, 5K/10K/HM/marathon predictions |
| `coros activities` | List workouts with filters |
| `coros activity <labelId> -s <code>` | Detailed metrics for one activity |
| `coros analyze <labelId> -s <code> [--focus "..."]` | Coach-style narrative analysis |

### `coros activities` filters

`--sport` accepts a group name, a numeric COROS sport-type code, or a
comma-separated mix:

- groups: `run`, `bike`, `swim`, `gym`, `ski`, `walk`, `row`, `climb`, `tri`, `all`
- codes: `100` outdoor run, `101` indoor run, `102` trail run, `200` outdoor bike, `201` indoor bike, `300` pool swim, `301` open water swim, `402` strength, `900` walk, `10000` triathlon… (full list: `coros mcp tools --json | jq '.[] | select(.name == "querySportRecords") | .description'`)

Other useful filters: `--min-km`, `--max-km`, `--min-min`, `--max-min`,
`--max-pace 5:30`, `--location <keyword>`, `--limit N`.

### Drilling into one activity

`coros activities` prints each workout's `LabelId` and `SportType`. Reuse
those with `coros activity` (raw metrics) or `coros analyze` (LLM-shaped
narrative; pass `--focus "pace stability"`, `"heart rate"`, etc. to bias it).

## Typical agent patterns

**"How did I sleep this week?"**

```bash
coros sleep --days 7
```

**"Show me my HRV trend over the last 30 days as JSON for plotting"**

```bash
coros hrv --days 30 --json
```

**"Am I overtraining?"**

Combine recovery + load + HRV:

```bash
coros recovery
coros load --days 14
coros hrv --days 14
```

**"Analyze my last long run"**

```bash
coros activities --sport run --min-km 8 --limit 1
# then plug LabelId + SportType into analyze
coros analyze <labelId> -s 100 --focus "pace stability"
```

**"What's my current VO2max and 10K prediction?"**

```bash
coros fitness
```

## Escape hatch

When the user asks something the wrapper commands don't expose (or COROS ships
a new MCP tool), drop to:

```bash
coros mcp tools                       # list tools
coros mcp call <toolName> --args '{...}' [--json]
```

## Caveats

- Empty results are normal for some metrics (HRV needs an overnight reading;
  `coros schedule` returns empty if the user has no plan).
- Timezones: COROS bucket dates by the watch's timezone; mismatched `--tz` can
  shift "yesterday" by one day. Default (system tz) is usually right.
- Read-only: the CLI cannot start workouts, sync files, or modify training
  plans. Tell the user so explicitly if they ask.
- The MCP server is regional. `coros auth` defaults to `eu`; other regions
  fall back to the EU host (the only published endpoint at time of writing).
