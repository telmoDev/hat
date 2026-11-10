#!/usr/bin/env bash
# Mirror the root's skills from .agents/skills/ (the source, which Codex reads) into .claude/skills/ (which
# Claude Code reads). Copies instead of symlinks, so it works on Windows without special permissions.
#   bash .orchestrator/scripts/sync-skills.sh          # copy every changed skill
#   bash .orchestrator/scripts/sync-skills.sh --check  # exit 1 if any copy differs from its source
# Skills listed in CODEX_ONLY_SKILLS (orchestrator.conf) are not copied: Claude Code has its own equivalent.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"  # the workspace root, whichever tool runs this
. "$root/.orchestrator/orchestrator.conf"
[ -d "$root/.claude" ] || exit 0  # no Claude Code adapter in this workspace
src="$root/.agents/skills" dst="$root/.claude/skills" check=no
[ "${1:-}" = "--check" ] && check=yes
[ -d "$src" ] || { echo "sync-skills: no $src" >&2; exit 2; }
status=0
for d in "$src"/*/; do
  name=$(basename "$d")
  case " ${CODEX_ONLY_SKILLS:-} " in *" $name "*) continue ;; esac
  if diff -rq -x '*.new' "$d" "$dst/$name" >/dev/null 2>&1; then continue; fi  # a .new is the update's, to merge
  if [ $check = yes ]; then echo "sync-skills: .claude/skills/$name differs from .agents/skills/$name"; status=1; continue; fi
  rm -rf "$dst/$name"; mkdir -p "$dst"; cp -R "$d" "$dst/$name"; find "$dst/$name" -name '*.new' -delete
  echo "sync-skills: copied $name"
done
exit $status
