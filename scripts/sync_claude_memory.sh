#!/usr/bin/env bash
#
# Sync this project's Claude Code memory between the local ~/.claude store and the
# repo, so it travels across machines via git.
#
#   scripts/sync_claude_memory.sh backup    # ~/.claude memory -> repo/.claude/memory (mirror)
#   scripts/sync_claude_memory.sh restore   # repo/.claude/memory -> ~/.claude memory (merge)
#
# Typical workflow:
#   machine A:  ...work...  ->  backup  ->  git add/commit/push
#   machine B:  git pull    ->  restore ->  start Claude (memory is loaded from ~/.claude)
#
# The live memory path is derived from THIS machine's repo path using Claude
# Code's munging (every "/" and "_" -> "-"), so it resolves correctly on each
# machine regardless of where the repo lives. If Claude stored its memory under
# a different path (e.g. you launched it from outside the repo), set
# CLAUDE_MEMORY_DIR to override.
set -euo pipefail

REPO="$(git rev-parse --show-toplevel)"
REPO_MEM="$REPO/.claude/memory"
LIVE="${CLAUDE_MEMORY_DIR:-$HOME/.claude/projects/$(printf '%s' "$REPO" | sed 's#[/_]#-#g')/memory}"

case "${1:-}" in
  backup)
    [ -d "$LIVE" ] || { echo "no live memory at: $LIVE" >&2; exit 1; }
    mkdir -p "$REPO_MEM"
    rsync -a --delete "$LIVE/" "$REPO_MEM/"
    echo "backed up:  $LIVE"
    echo "        ->  $REPO_MEM  ($(find "$REPO_MEM" -type f | wc -l) files)"
    echo "now: git add .claude/memory && git commit && git push"
    ;;
  restore)
    [ -d "$REPO_MEM" ] || { echo "no repo memory at: $REPO_MEM (git pull first?)" >&2; exit 1; }
    mkdir -p "$LIVE"
    # merge (no --delete): never destroys local memory that hasn't been backed up.
    # for an exact mirror instead, add --delete.
    rsync -a "$REPO_MEM/" "$LIVE/"
    echo "restored:  $REPO_MEM"
    echo "       ->  $LIVE  ($(find "$LIVE" -type f | wc -l) files)"
    ;;
  *)
    echo "usage: $0 {backup|restore}" >&2
    exit 1
    ;;
esac
