<!-- mcp-name: io.github.dengxuhui/igpsport-mcp -->
# igpsport-mcp

**English** | [简体中文](https://github.com/dengxuhui/igpsport-mcp/blob/main/README.zh-CN.md)

A local [MCP](https://modelcontextprotocol.io) server that connects your **iGPSport cycling data** to LLM clients like Claude. Analyze your training in natural language: *"How's my training load this week?"* *"Compare my two long rides from last week and this week."* *"What's my ranking on that climb I starred?"* *"How many kilometers did I ride this year, and what are my personal bests?"* — and even **have Claude prescribe workouts for you**: *"Build me a 2×20 SST session based on my FTP and push it to my head unit."*

**Key differentiator**: Derived training metrics — NP / IF / TSS / CTL / ATL / TSB — are **computed server-side in the MCP layer** before being returned. The LLM receives story-ready numbers, not raw stream data.

```
You:   What's my training load trend over the last 90 days? Should I back off?
Claude (via analyze_training_load):
       Current CTL (Fitness) 72, ATL (Fatigue) 91, TSB (Form) -19 — you're in a significant fatigue hole.
       TSS has been above CTL for the past two weeks. Consider a 3–5 day recovery block to get TSB back above -5…
```

## Demo

![igpsport-mcp demo](assets/demo.gif)

> ⚠️ **Unofficial project**. This tool works by **simulating iGPSport web client requests**. iGPSport may change their API at any time, which could break functionality. Please evaluate account risk yourself — **use at your own risk**. Runs entirely locally over stdio — **your data never touches any third-party server**.

## Quick Start (Recommended)

This tool is an MCP server and requires an **MCP-capable client** (e.g. [Claude Desktop](https://claude.ai/download) / Claude Code / Cursor). Once you have a client ready, three steps:

**1. Install uv** (a standalone tool — **you do not need Python pre-installed**, uv handles the runtime automatically):

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**2. Install globally and run the setup wizard** (interactively enter your phone/email and password — credentials stay local). The commands are the same on both systems; run them in **Terminal** on macOS or **PowerShell** on Windows:

```bash
uv tool install igpsport-mcp
igpsport-mcp --setup
```

> If `igpsport-mcp` is not found after installation, open a new terminal/PowerShell window so PATH updates take effect (uv places executables in `~/.local/bin` on macOS, `%USERPROFILE%\.local\bin` on Windows).

The wizard saves credentials to a config file (owner-readable only) and prints a **copy-paste ready** MCP configuration block. Config file locations:

- **macOS**: `~/.igpsport-mcp/config.json`
- **Windows**: `C:\Users\YourName\.igpsport-mcp\config.json`

**3. Paste the printed config into your client**, then restart the client (see "Connect to Claude" below).

> Want to verify your credentials before pasting? Run `igpsport-mcp --check` — it performs a real login and prints ✅ success or ❌ the reason for failure, so you don't add it to your client only to find it broken.
>
> Need to print the config snippet again later? `igpsport-mcp --mcp-config` anytime.

---

> Developers / users with an existing Python environment: use `uvx igpsport-mcp` for one-shot runs, or configure via environment variables below instead of the wizard.

## CLI Usage

Running with no arguments starts the MCP server in stdio mode (this is what your MCP client invokes — you normally don't run it manually). Other subcommands:

| Command | Purpose |
|---|---|
| `igpsport-mcp --setup` | Interactive setup wizard: enter phone/email + password, saved to local config.json |
| `igpsport-mcp --mcp-config` | Print a copy-paste ready MCP client configuration block |
| `igpsport-mcp --check` | Perform a real login to verify credentials (account is shown masked) |
| `igpsport-mcp --lang en\|zh` | Set output language (also settable via `IGPSPORT_LANG` env var; default `zh`) |
| `igpsport-mcp --version` | Print version number |
| `igpsport-mcp --help` | Show help |

## Configuration (Environment Variables)

> Users who ran the `--setup` wizard **can skip this section** — credentials are already stored. The section below is for users who prefer environment variables, or need to manage credentials across CI / multiple environments. Env vars take priority over config.json.

| Variable | Required | Description |
|---|---|---|
| `IGPSPORT_USERNAME` | ✅ | iGPSport account (phone number for CN / email for international) |
| `IGPSPORT_PASSWORD` | ✅ | Password |
| `IGPSPORT_REGION` | Optional | Region, default `cn` (China server `app.igpsport.cn`); international users set `intl` (`app.igpsport.com`) |
| `IGPSPORT_FTP` | Optional | Functional Threshold Power in watts. **Leave blank to auto-read from your iGPSport profile**; set to override |
| `IGPSPORT_LTHR` | Optional | Lactate Threshold Heart Rate in bpm, used for HR zones and hrTSS fallback. **Also auto-read from iGPSport**; set to override |
| `IGPSPORT_LANG` | Optional | Output language, `zh` (default) or `en` |
| `IGPSPORT_CACHE_DIR` | Optional | Cache directory; defaults to `~/.cache/igpsport-mcp` (macOS) / `C:\Users\You\.cache\igpsport-mcp` (Windows) |
| `IGPSPORT_LOG_LEVEL` | Optional | Default `INFO` |

> FTP / LTHR are now **auto-read from your iGPSport athlete profile** by default (along with body weight and max HR), so you normally **don't need to set them manually**. Only set the env vars when you want to use thresholds different from what's in the app. If your iGPSport profile also has no FTP set, IF / TSS / CTL / ATL / TSB cannot be computed — either add FTP in iGPSport or set `IGPSPORT_FTP`.

## International Edition Support

Switch to the international edition (`app.igpsport.com`) by setting `IGPSPORT_REGION=intl`. The international and China servers use **separate accounts** — you must register separately at `app.igpsport.com`.

**Differences from the China server**:

- No WASM signing — authentication uses pure JWT, a simpler design
- **Segment features are unavailable** (international segments are in beta, listing is empty)
- Training parameter endpoint uses v2 path; yearly statistics path differs (auto-adapted internally)
- Workout course format is cross-region compatible — zero changes in the IR compilation layer

Example configuration:

```bash
# via env vars
export IGPSPORT_REGION=intl
export IGPSPORT_USERNAME=your_email@example.com
export IGPSPORT_PASSWORD=your_password
```

Or select "2. International" in the first step of the `--setup` wizard.

> International edition FIT files are stored on OSS in the US (`oss-us-west-1`). Downloads may be slightly slower for users in China.

## Connect to Claude

### Claude Desktop

Open the config file `claude_desktop_config.json` (create it if it doesn't exist), paste the content below, then **fully quit and reopen** Claude Desktop. File locations:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json` (i.e. `C:\Users\You\AppData\Roaming\Claude\claude_desktop_config.json`)

> You can also open this file directly from Claude Desktop via **Settings → Developer → Edit Config**.

**After running `--setup`** (credentials in config.json, leave `env` empty — this is what `--mcp-config` prints):

```json
{
  "mcpServers": {
    "igpsport": {
      "command": "igpsport-mcp",
      "args": [],
      "env": {}
    }
  }
}
```

**Or** skip the wizard and use `uvx` with environment variables:

```json
{
  "mcpServers": {
    "igpsport": {
      "command": "uvx",
      "args": ["igpsport-mcp"],
      "env": {
        "IGPSPORT_USERNAME": "your_phone_or_email",
        "IGPSPORT_PASSWORD": "your_password"
      }
    }
  }
}
```

> FTP / LTHR are auto-read from your iGPSport profile by default — no need to set them. Only add `"IGPSPORT_FTP": "250"` or `"IGPSPORT_LTHR": "160"` in `env` if you want to override what's in the app.

### Claude Code

After the wizard (credentials stored):

```bash
claude mcp add igpsport --scope user -- igpsport-mcp
```

Or with uvx + env vars:

```bash
claude mcp add igpsport --scope user \
  --env IGPSPORT_USERNAME=your_phone_or_email \
  --env IGPSPORT_PASSWORD=your_password \
  -- uvx igpsport-mcp
```

Verify with `/mcp` or `claude mcp list` — status should be `connected`.

### OpenClaw

[OpenClaw](https://github.com/openclaw/openclaw) uses stdio for MCP, the same protocol as Claude Desktop / Claude Code, so the configuration above works directly.

**Method 1: Ask OpenClaw in natural language (recommended)**

First install with `uv tool install igpsport-mcp` and run `igpsport-mcp --setup`. Then, in your connected chat channel, simply tell OpenClaw:

> I installed igpsport-mcp. Help me configure it in OpenClaw.

It will locate the binary path, verify credentials with `igpsport-mcp --check`, write the config via `openclaw mcp add`, and probe it — all without you touching a command line or JSON.

**Method 2: One-liner**

```bash
# After the wizard (credentials stored)
openclaw mcp add igpsport --command igpsport-mcp

# Or with uvx + env vars
openclaw mcp add igpsport --command uvx --args igpsport-mcp \
  --env IGPSPORT_USERNAME=your_phone_or_email \
  --env IGPSPORT_PASSWORD=your_password
```

This writes to `~/.openclaw/openclaw.json` under `mcp.servers.igpsport`. You can also edit the file manually:

```json5
{
  mcp: {
    servers: {
      igpsport: {
        command: "igpsport-mcp",
        args: [],
        env: {}
      }
    }
  }
}
```

Verification:

```bash
openclaw mcp list      # should show igpsport
openclaw mcp status    # igpsport: stdio
openclaw mcp probe     # igpsport: 17 tools, resources, prompts
```

The `mcp` field is hot-reloaded — no gateway restart needed; it takes effect in the next conversation turn. Use `openclaw mcp reload` to force-refresh the runtime cache if needed. Then ask questions in natural language from any connected channel (Discord, Telegram, Slack, etc.).

> **Not connecting?** Run `igpsport-mcp --check` in a terminal first to isolate the problem:
> - ❌ Login failed → credential issue; re-run `igpsport-mcp --setup`.
> - ✅ Success but the client still can't connect → likely `igpsport-mcp` / `uvx` isn't in the client's PATH (Claude Desktop in particular often can't see the login shell's PATH). Replace `command` in the config with the **absolute path**:
>
> - **macOS**: run `which igpsport-mcp` (or `which uvx`) in Terminal, e.g. `/Users/You/.local/bin/igpsport-mcp`.
> - **Windows**: run `where.exe igpsport-mcp` (or `where.exe uvx`) in PowerShell, e.g. `C:\Users\You\.local\bin\igpsport-mcp.exe`. In JSON, backslashes must be doubled, e.g. `"command": "C:\\Users\\You\\.local\\bin\\igpsport-mcp.exe"`.

## Updates

**For `uv tool install` installations** (both systems), upgrade to the latest:

```bash
uv tool upgrade igpsport-mcp
```

Restart your client after upgrading (fully quit and reopen Claude Desktop; reconnect for Claude Code). Check current version: `igpsport-mcp --version`.

> **For `uvx igpsport-mcp` one-shot users**, no manual upgrade is needed — uvx uses the latest version by default. If a stale version is cached locally, use `uvx igpsport-mcp@latest` or clear the cache with `uv cache clean` first.

## Uninstall

**1. Remove the program** (same for both systems):

```bash
uv tool uninstall igpsport-mcp
```

**2. Remove local credentials and cache** (optional, for a complete cleanup):

```bash
# macOS / Linux (Terminal)
rm -rf ~/.igpsport-mcp        # credentials (config.json)
rm -rf ~/.cache/igpsport-mcp  # tokens, SQLite, FIT file cache
```

```powershell
# Windows (PowerShell)
Remove-Item -Recurse -Force "$env:USERPROFILE\.igpsport-mcp"
Remove-Item -Recurse -Force "$env:USERPROFILE\.cache\igpsport-mcp"
```

**3. Remove `igpsport` from your client config**: Claude Desktop — delete the `igpsport` block under `mcpServers` in `claude_desktop_config.json`; Claude Code — `claude mcp remove igpsport`; OpenClaw — `openclaw mcp unset igpsport` (or delete the `igpsport` block under `mcp.servers` in `~/.openclaw/openclaw.json`).

> For `uvx igpsport-mcp` one-shot users, there is no "program" to uninstall — just do steps 2 and 3.

## 17 Tools Provided

**Activities & Training (9)**

| Tool | Purpose |
|---|---|
| `list_activities` | List activities (supports date range, pagination) |
| `get_activity_summary` | Single-activity derived metrics: NP / IF / TSS / work, HR & power zone time-in-zone |
| `get_activity_streams` | Time-series data (enforced downsampling + channel selection, token-friendly) |
| `get_activity_laps` | Lap / segment data (per-lap NP) |
| `get_athlete_profile` | Training parameters: FTP / LTHR (auto-read from iGPSport or overridden via env vars); body weight and max HR always from iGPSport; includes zone boundaries |
| `get_athlete_stats` | Period-aggregated statistics (computed locally from activity list) |
| `estimate_thresholds` | Estimate FTP / LTHR from recent rides' mean-max curves for riders who haven't done a formal test (Coggan 20-min, critical-power cross-check, Friel HR field test); each value carries a confidence level + evidence + a "confirm with a formal test" caveat. Read-only — never writes back, the rider applies it manually |
| `compare_activities` | Compare multiple activities (2–5) |
| `analyze_training_load` | CTL / ATL / TSB trend + form interpretation (the killer query) |

**Segments (3)**

| Tool | Purpose |
|---|---|
| `list_segments_collected` | List starred segments with your best time |
| `get_segment_detail` | Segment details: distance / gradient / elevation gain + KOM + fastest leaderboard + your PR |
| `get_segment_rank` | Segment leaderboard (`query_type` 1=overall, 2=yearly, etc.), includes your rank |

**Statistics & Achievements (1)**

| Tool | Purpose |
|---|---|
| `get_member_statistics` | Official yearly statistics & personal bests: total distance / duration / calories / TSS, monthly distance, distance milestones, various PRs (longest / longest duration / fastest / max power / max elevation) |

**Training Courses (4)** — the only "write" capability

| Tool | Purpose |
|---|---|
| `create_workout` | Describe a structured training session in natural language (warmup / main set / intervals / cooldown), compile it to iGPSport's native format, and push it to your head unit app; supports `dry_run=true` to preview without sending; `with_calendar=true` additionally returns a standard iCalendar (`VEVENT`) artifact for downstream tools like Apple Calendar, Reminders, or Notion |
| `list_workouts` | Pull all custom workouts from the server in real time (reflects deletions made in the app) |
| `get_workout_detail` | Fetch the full structure of a specific workout |
| `delete_workout` | Delete a workout. **Destructive and irreversible**: defaults to a confirmation preview; requires explicit `confirm=true` to actually delete |

> Power targets support absolute watts, %FTP (auto-converted using your FTP), and power zones; heart rate, cadence, and speed targets are also supported. Duration can be set by time / distance / calories / manual lap button. Created workouts appear in the iGPSport app under "Training Courses" and can be synced to your head unit for execution.

## Derived Metrics Reference

- **NP** (Normalized Power): `((30 s rolling average power)^4 mean)^0.25`; stream is resampled to 1 Hz before computation.
- **IF** = NP / FTP; **TSS** = `duration_s × NP × IF / (FTP × 3600) × 100`.
- **CTL / ATL / TSB**: exponential weighted moving averages of daily TSS (α = 1/42, 1/7); TSB = CTL − ATL.
- **No-power-meter fallback**: hrTSS = `(duration_s / 3600) × (avg HR / LTHR)² × 100`, annotated `estimated from HR`.
- **Zone models**: HR uses Friel (LTHR-based); Power uses Coggan 7-zone (FTP-based).

## FAQ

**Q: Do I need a power meter?**
A: No. Without a power meter, heart-rate-based metrics work normally and TSS falls back to hrTSS (lower accuracy, annotated as such). However, setting FTP is recommended to unlock power-based metrics.

**Q: Is my data uploaded anywhere?**
A: Not to any third party. Other than reading/writing **your own** iGPSport account data (reading activities/stats, and `create_workout`/`delete_workout` for your own training courses), everything happens locally. FIT files and derived metrics are cached locally.

**Q: Can `create_workout` / `delete_workout` mess up my data?**
A: `create_workout` only adds new training courses — you can use `dry_run=true` to preview the compiled result before deciding to send. `delete_workout` is irreversible and defaults to a confirmation preview; it requires explicit `confirm=true` to actually delete — so an LLM cannot delete a course without your confirmation.

**Q: Does `with_calendar` automatically write to my calendar?**
A: No. This server **only produces** a standard iCalendar (`VEVENT`) text artifact — it never touches any calendar API or sends data externally. Whether the event is actually written to a calendar is up to your LLM client to hand off to another calendar/reminder tool (e.g. Apple Calendar, Reminders, or a Notion MCP). Since a workout is a template with no execution date, the `DTSTART` is the placeholder `{{SCHEDULED_DATE}}` — the downstream consumer fills in the actual date.

**Q: What if the API breaks?**
A: iGPSport may change their API, which could cause breakage — the tool will throw a clear error. Please report issues at [Issues](https://github.com/dengxuhui/igpsport-mcp/issues).

**Q: Does it support running / other head units?**
A: No. This project focuses exclusively on iGPSport cycling data.

**Q: What's different about the international edition?**
A: International and China server accounts are separate. The international edition lacks segment features (beta, listing is empty) and uses a simpler authentication mechanism (no WASM signing). Activities, training courses, and statistics work the same. See the "International Edition Support" section for details.

## Development

```bash
uv sync --extra dev
uv run pytest            # tests
uv run pytest -m integration   # online integration tests
ruff check . && ruff format .  # lint / format
```

## License

[MIT](LICENSE). This project is not affiliated with iGPSport in any way.
