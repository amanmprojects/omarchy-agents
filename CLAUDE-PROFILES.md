# Claude profile tracking

This fork is enabled as the `aman.agents` plugin. Its Claude collector
(`bin/omarchy-agent-usage-claude-profiles`) wraps Omarchy's installed
collector and extends only the project scan.

## Roots

Local usage combines:

- `$CLAUDE_CONFIG_DIR/projects`, when set
- `~/.claude/projects`
- every immediate `~/.claude-profiles/*/projects` directory

All roots feed one scan, so message IDs and session IDs are deduplicated
across copied transcripts instead of being counted once per profile. New
profile directories are discovered on each update. The scan cache key includes
the resolved root list, so adding a profile invalidates the old cache.

`~/.claude-profiles/200"` and `~/.claude-profiles/zen` have no `projects`
directory and are skipped.

## Limits stay primary

Authentication, rate limits, and account switching still use the primary
Claude directory (`CLAUDE_CONFIG_DIR` or `~/.claude`). Limits are **not**
combined across profiles. The panel shows one Claude tab with combined local
tokens and the primary account's limits.

## Refresh

```sh
omarchy-shell aman.agents refresh
```

or run the updater directly:

```sh
~/.config/omarchy/plugins/aman.agents/bin/omarchy-agent-usage-update-profiles --force claude
```

## Restore the stock widget

```sh
omarchy plugin disable aman.agents
omarchy plugin enable omarchy.agents
```

## Maintenance

The adapter loads `/usr/share/omarchy/bin/omarchy-agent-usage-claude` at
runtime. If Omarchy changes the collector's `is_dir`/`rglob` view interface or
the `cached_scan(projects_path, max_age_seconds)` signature, update the adapter.
