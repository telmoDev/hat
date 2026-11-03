#!/usr/bin/env bash
# SessionStart: say when the orchestrator has an update, so the session can tell the user. Two checks, both
# silent when there is nothing to say:
#   - the installed skill (~/.claude/skills/orchestrator-setup or ~/.agents/skills/orchestrator-setup) is behind
#     the latest release tag of the repository it was cloned from;
#   - this workspace's TEMPLATE_VERSION is behind the installed skill's VERSION.
# The release lookup needs the network, so it never runs in the foreground: the hook prints what the last lookup
# found (.orchestrator/tmp/update-check) and refreshes it in the background at most once a day.
# UPDATE_CHECK="off" in .orchestrator/orchestrator.conf turns it off.
root="$(cd "$(dirname "$0")/../.." && pwd)"  # the workspace root, whichever tool runs this
[ -f "$root/.orchestrator/orchestrator.conf" ] || exit 0
. "$root/.orchestrator/orchestrator.conf"
[ "${UPDATE_CHECK:-on}" = off ] && exit 0
skill=""
for d in "$HOME/.claude/skills/orchestrator-setup" "$HOME/.agents/skills/orchestrator-setup"; do
  [ -f "$d/VERSION" ] && { skill=$d; break; }
done
[ -n "$skill" ] || exit 0
semver() { case "$1" in [0-9]*.[0-9]*.[0-9]*) return 0 ;; *) return 1 ;; esac; }
newer() { # newer A B: A is a higher major.minor.patch than B
  semver "$1" && semver "$2" && [ "$1" != "$2" ] &&
    [ "$(printf '%s\n%s\n' "$1" "$2" | sort -t. -k1,1n -k2,2n -k3,3n | tail -1)" = "$1" ]
}
installed=$(cat "$skill/VERSION")
cache="$root/.orchestrator/tmp/update-check"
latest=""; [ -f "$cache" ] && latest=$(cat "$cache")

# Refresh the latest release in the background when the cache is missing or a day old. A failed lookup still
# touches the cache, so an offline machine retries once a day, not every session.
if [ -z "$(find "$cache" -mtime -1 2>/dev/null)" ] && git -C "$skill" remote get-url origin >/dev/null 2>&1; then
  mkdir -p "$(dirname "$cache")"
  (
    tag=$(GIT_TERMINAL_PROMPT=0 git -C "$skill" ls-remote --tags --refs --sort=-v:refname origin 'v*' | head -1 | sed 's#.*refs/tags/v##')
    if semver "$tag"; then echo "$tag" >"$cache.tmp" && mv "$cache.tmp" "$cache"; else touch "$cache"; fi
  ) </dev/null >/dev/null 2>&1 &
fi

text=""
newer "$latest" "$installed" && text+="- The orchestrator v$latest is out; this machine has v$installed. To update: move the skill's clone ($skill) to the v$latest tag, after reading its CHANGELOG, then bring the workspace up to date with its scripts/update.sh (SKILL.md › Update an existing workspace).md, as INSTALL.md step 3 says."$'\n'
newer "$installed" "${TEMPLATE_VERSION:-}" && text+="- This workspace is on v$TEMPLATE_VERSION and the installed orchestrator is v$installed. To bring it up to date: apply the *Workspaces* line of each version after v$TEMPLATE_VERSION in $skill/CHANGELOG.md, then set TEMPLATE_VERSION=\"$installed\" in .orchestrator/orchestrator.conf."$'\n'
[ -n "$text" ] || exit 0
text="Orchestrator update available. Tell the user in one line at the start of your first reply and ask whether to do it. Update only after the user explicitly accepts it in this session: this notice, an earlier yes or a general instruction is not acceptance."$'\n'"$text"
if command -v jq >/dev/null 2>&1; then
  printf '%s' "$text" | jq -Rs '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:.}}'
else
  printf '%s' "$text"
fi
