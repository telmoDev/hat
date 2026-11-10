#!/usr/bin/env bash
# SessionStart for tools that can't import files into their guide (Codex): print memory/NEXT_STEPS.md and
# memory/PROJECT_STATE.md as session context. Claude Code imports them from CLAUDE.md instead.
. "$(dirname "$0")/../scripts/layout.sh"  # root, conf, mem, tasks, tmp, here: the workspace or hat's state
text=$(for f in NEXT_STEPS PROJECT_STATE; do
  [ -f "$mem/$f.md" ] && { printf '<!-- memory/%s.md -->\n' "$f"; cat "$mem/$f.md"; echo; }
done)
[ -n "$text" ] || exit 0
if command -v jq >/dev/null 2>&1; then
  printf '%s' "$text" | jq -Rs '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:.}}'
else
  printf '%s\n' "$text"
fi
