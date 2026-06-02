# Claude Code state (synced)

`memory/` is a git-tracked mirror of this project's Claude Code memory (which
normally lives only in `~/.claude/projects/<munged-path>/memory/`). It's committed
here so the project's accumulated context travels across machines.

- **On a new/other machine, after `git pull`:** run
  `./scripts/sync_claude_memory.sh restore` to copy it into `~/.claude` so Claude
  loads it. (Auto-detects the path if the repo is at the same absolute location,
  e.g. `/home/zagreus/nj_sandy_sfincs`; otherwise set `CLAUDE_MEMORY_DIR`.)
- **After a session that updated memory:** run
  `./scripts/sync_claude_memory.sh backup`, then commit & push.

`settings.local.json` is intentionally NOT tracked (personal/machine-local).
