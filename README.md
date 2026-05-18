# coros-cli

Unofficial Python CLI to extract sleep metrics from your [Coros Training Hub](https://t.coros.com) account.

Not affiliated with Coros. Uses your own credentials against Coros's private APIs (reverse-engineered from the mobile app).

## Install

```sh
uv sync
uv run coros --help
```

## Quickstart

```sh
uv run coros login                      # once, interactive prompt
uv run coros sleep --days 14 --yes      # weekly refresh (kicks the phone app once)
uv run coros sleep --offline --json     # read cache from then on, no network
```

## Commands

### `coros login`

Interactive email + password prompt. Stores:

- Web access token + `userId` (needed for HRV fetch).
- `pwd_hash` (MD5 of password — never the plaintext).
- Region, auto-detected (`eu`/`us`/`asia`/`cn`).

File: `~/.config/coros-cli/config.json`, mode `0600`.

Re-run if you change password or switch account. The CLI self-heals a missing `userId` on any later `sleep` refresh, so you don't need to re-run `login` just because the auth file predates a CLI update.

Flag `--with-mobile` forces the mobile login immediately (disconnects the Coros app on your phone). Omit it to defer the kick until the first `sleep` refresh.

### `coros sleep`

Display sleep records. Reads from a local cache, refreshing on demand.

```sh
coros sleep                                    # last 7 days from cache
coros sleep --from 2026-04-01 --to 2026-04-14  # explicit range
coros sleep --days 30 --json                   # 30 days as JSON
coros sleep --force --yes                      # force refresh, no prompt
coros sleep --offline                          # cache-only; exit 2 if stale
```

#### Cache

- File: `~/.config/coros-cli/data/sleep.json` (mode `0600`)
- Per-day records keyed by `YYYYMMDD` + a `synced_at_ms` timestamp.
- TTL for automatic refresh: **7 days**. Requests within that window read straight from cache.

A refresh is triggered when any of these is true:

- Cache file missing.
- `synced_at_ms` older than 7 days.
- Any day in the requested range is not cached.
- `--force` passed.

A refresh performs: mobile login → pull sleep stages → pull HRV via web API → merge into cache. The mobile login **disconnects the Coros app from your phone** (Coros enforces one active mobile session per account). The CLI prompts `[y/N]` before kicking, unless `--yes` / `-y` is passed.

`--offline` forbids network access entirely. If a refresh would be required, the CLI exits with code `2`. Use this in automation that must never disrupt the phone session.

#### JSON schema

`coros sleep --json` emits a list:

```json
[
  {
    "date": "20260414",
    "total_minutes": 430,
    "phases": {
      "deep_minutes": 95,
      "light_minutes": 245,
      "rem_minutes": 70,
      "awake_minutes": 20,
      "nap_minutes": null
    },
    "avg_hr": 52,
    "min_hr": 46,
    "max_hr": 68,
    "hrv_avg": 58
  }
]
```

All numeric fields may be `null`. `hrv_avg` is overnight HRV as rmssd in milliseconds, sourced from the Coros web API `/analyse/dayDetail/query` endpoint.

#### Exit codes

| Code | Meaning                                                        |
| ---- | -------------------------------------------------------------- |
| 0    | Success                                                        |
| 1    | Not logged in, API error, user aborted refresh                 |
| 2    | `--offline` set and cache insufficient for the requested range |

## MCP (experimental)

Experimental commands for talking to a COROS MCP server over OAuth 2.0. Independent of `coros login` — no phone session is touched.

```sh
coros mcp auth                          # OAuth flow, store credentials
coros mcp status                        # show token state / expiry
coros mcp tools --json                  # list server tools as JSON
coros mcp call TOOL --args '{}'         # invoke a tool with JSON args
coros mcp revoke                        # revoke tokens and delete credentials
```

### `coros mcp auth`

Uses the OAuth 2.0 **authorization-code grant with PKCE**. `coros mcp auth`:

1. Dynamically registers a public client and prints an authorization URL.
2. You open that URL, sign in to COROS, and approve access — no password is handled by coros-cli.
3. After approval the browser is redirected to a loopback URL (`http://localhost:8765/callback?code=…`). **coros-cli runs no local server, so that page will fail to load (“connection refused”) — this is expected.**
4. Copy the full URL from the browser address bar and paste it back into the prompt (pasting just the `code` value also works). The `state` parameter is verified for CSRF protection when a full URL is pasted.

Credentials live in `~/.config/coros-cli/mcp-oauth.json` (mode `0600`), separate from the mobile-login auth in `config.json`.

`sleep` refresh has **not** been migrated to MCP — it still uses the mobile/web APIs. Migration waits until the real COROS tool schemas are known.

## Recommended agent workflow

```sh
# Human or weekly scheduled task — one kick per week is acceptable.
coros sleep --days 14 --yes

# Agents reading data throughout the week — never touches the network.
coros sleep --offline --json --from 2026-04-08 --to 2026-04-14
```

If `--offline` exits with code `2`, the agent should either:

1. Fall back to the partial cache by re-running without `--offline --from/--to` to see what's actually stored, or
2. Surface the issue to the human so they trigger the weekly sync.

## Files on disk

| Path                                  | Purpose                                               |
| ------------------------------------- | ----------------------------------------------------- |
| `~/.config/coros-cli/config.json`     | Stored auth (email, pwd_hash, tokens, userId, region) |
| `~/.config/coros-cli/data/sleep.json` | Sleep records cache                                   |
| `~/.config/coros-cli/mcp-oauth.json`  | MCP OAuth credentials (experimental)                  |

Both are `0600`. The plaintext password is never stored — only its MD5 hash, which is the credential shape Coros's API itself expects.

## Why does a refresh disconnect my phone?

Coros's mobile API enforces a single active session per account. Any mobile login from the CLI invalidates the token held by the Coros app on your phone, and vice versa. The web API (activities, HRV) does not have this constraint — but sleep stages are only exposed on the mobile API, so any CLI that pulls sleep must accept the tradeoff.

The cache + 7-day TTL means you trade one deliberate phone reconnect per week for all your queries in between. Re-open the Coros app and log back in after each sync.

## Dev

```sh
uv run pytest           # tests
uv run ruff check .     # lint
uv run ruff format .    # format
uv run mypy src         # types
```

## Implementation notes

Two APIs are involved:

- **Web** (`teameuapi.coros.com`, regional variants): login via MD5(pwd); `accesstoken` + `yfheader: {userId}` headers. Used for HRV via `/analyse/dayDetail/query`.
- **Mobile** (`apieu.coros.com`): login with AES-128-CBC payload, XOR-derived key, IV `weloop3_2015_03#` (reverse-engineered from the Coros APK). Sleep via `POST /coros/data/statistic/daily`. Single active session per account.

`scripts/probe_hrv.py` dumps the raw `/analyse/dayDetail/query` response — useful when HRV extraction needs debugging.
