# Agents for Omarchy

A maintained fork of Omarchy's `omarchy.agents` bar widget. It keeps the
upstream panel and adds the things this machine actually needs:

- **Claude profiles** — local usage from `~/.claude` and every
  `~/.claude-profiles/*/projects` directory, deduplicated across copied
  sessions.
- **OpenCode** — local usage from OpenCode's SQLite stores, including the
  older `message` table and the newer `session_message` table, with cost and
  provider breakdowns.
- **Self-contained collectors** — the updater lives in `bin/` inside the
  plugin, so `omarchy plugin update` updates the panel and its collectors
  together. No `~/.local/bin` install step.

The panel is still a display. It watches the JSON records in
`~/.local/state/omarchy/agents/usage/` and draws every record that appears.
`Panel.qml` owns the bar button and popup; `Main.qml`
discovers and watches records; `Agent.qml` is the per-record file watcher.

## Install

```sh
omarchy plugin disable omarchy.agents
omarchy plugin add https://github.com/amanmprojects/omarchy-agents --enable
```

The plugin id is `aman.agents`. If an older local clone also uses that id,
remove it first (or move it aside); the plugin loader only allows one plugin
per id.

```sh
rm -rf ~/.config/omarchy/plugins/aman.agents.profiles
```

Update with:

```sh
omarchy plugin update aman.agents
```

## Panel

- **Hero** — the mark, the tool, and the plan it runs on.
- **Subscription switch** — one chip per enabled agent (`h`/`l` or click).
  It appears only when more than one agent has data.
- **Limits** — allowance percentage, meter, and reset countdown when the
  collector reports them.
- **Balance** — prepaid agents show a credit ledger instead of limits.
- **Tokens by day** — the last week, one row per day, today bolded.
- **Tokens by model** — the heaviest four models, with input/output/cache
  detail on hover.

An agent appears only when it is enabled and has recorded usage. With no
data, the whole module leaves the bar rather than sitting there empty.

## Data

Each agent is one JSON record in `~/.local/state/omarchy/agents/usage/`.
`omarchy-agent-usage-update-profiles` runs:

1. Omarchy's stock updater with `claude` and `opencode` excluded, so Codex,
   Fireworks, Grok, Kimi, and future stock collectors keep working.
2. `bin/omarchy-agent-usage-claude-profiles`, which wraps the installed
   Claude collector and adds the profile roots.
3. `bin/omarchy-agent-usage-opencode`, which reads OpenCode's local database.

Records are written atomically and keep the same contract as Omarchy's
collectors, so the panel needs no provider-specific QML.

| Collector | Limits | Local stats |
|---|---|---|
| `claude` | Anthropic OAuth usage endpoint (5-hour + 7-day) | `~/.claude/projects`, every `~/.claude-profiles/*/projects`, plus the stock fallbacks |
| `opencode` | none yet | `~/.local/share/opencode/opencode.db` (`message` + `session_message`), deduplicated by message id |
| `codex` | Codex app-server RPC | native Codex sessions, pi, and opencode sessions on an OpenAI provider |
| `fireworks` | estimated prepaid balance | Fireworks billing API |
| `grok`, `kimi` | stock Omarchy collectors | stock Omarchy collectors |

### Claude profiles

The wrapper loads Omarchy's installed collector at runtime and swaps only its
project scan. One scan sees every root, so message IDs and session IDs are
deduplicated across profiles instead of being summed. New profile directories
are discovered on each update, and the scan cache key includes the resolved
root list.

Authentication and rate limits still use the primary Claude directory
(`CLAUDE_CONFIG_DIR` or `~/.claude`). Limits are **not** combined across
profiles or accounts.

### OpenCode

OpenCode stores sessions in SQLite. Current releases use
`session_message`, while older data and a partial migration remain in
`message`; the collector reads both and keeps the copy with the most usage for
any duplicate message id. Paths:

- `$OPENCODE_DATA_HOME/opencode.db`
- otherwise `$XDG_DATA_HOME/opencode/opencode.db`
- otherwise `~/.local/share/opencode/opencode.db`

There are no OpenCode subscription limits yet, so the OpenCode tab shows
local stats only. The record also carries `costUsd`, `providerUsage`, and
per-model cost, ready for profile/provider views.

## Settings

Settings live in the widget's `aman.agents` entry in
`~/.config/omarchy/shell.json`:

```bash
omarchy bar set aman.agents refreshIntervalSec 300 --json
omarchy bar set aman.agents providers '{
  "claude": { "enabled": true },
  "codex": { "enabled": true },
  "opencode": { "enabled": true },
  "fireworks": { "enabled": false }
}' --json
```

| Key | Default | What it does |
|---|---|---|
| `refreshIntervalSec` | `900` | How often records regenerate |
| `syncMode` | `"Off"` | `"On"` writes this machine's snapshot and merges others |
| `syncDir` | `""` | A folder synced by Syncthing, Dropbox, rsync, … |
| `syncFileName` | `<hostname>.json` | This machine's snapshot file |
| `syncDeviceId` | hostname | Stable device name inside the snapshot |

IPC:

```sh
omarchy-shell aman.agents refresh
omarchy-shell aman.agents toggle
```

With `syncMode` on, every `*.json` snapshot in `syncDir` is merged. Rate
limits and balances stay per-account and never travel.

## Development

```sh
python3 -I tests/test_opencode_collector.py -v
omarchy-plugin-validate .
```

The Claude adapter loads `/usr/share/omarchy/bin/omarchy-agent-usage-claude`
at runtime. If Omarchy changes `is_dir`/`rglob` or
`cached_scan(projects_path, max_age_seconds)`, update
`bin/omarchy-agent-usage-claude-profiles`.

## Roadmap

- A profile manager inside the panel: add/remove Claude profile roots and
  enable/disable them without editing settings.
- Per-profile usage and limits, instead of one combined Claude tab.
- Per-provider OpenCode usage (the collector already emits
  `providerUsage`).
- OpenCode Zen limits when an account-scoped usage endpoint is available.

## Credits

The widget is Omarchy's MIT-licensed Agents plugin. This fork adds the profile
adapter, the OpenCode collector, and the self-contained updater. Upstream:
<https://github.com/basecamp/omarchy>.
