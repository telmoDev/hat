#!/usr/bin/env bash
# Session handoff hook: passes the hook's stdin to .orchestrator/scripts/session_handoff.py <start|end>.
# "start" may print the last session's draft as context (only when that session didn't update memory/); "end"
# prints nothing. Never fails the session. SESSION_HANDOFF="off" in orchestrator.conf turns it off.
. "$(dirname "$0")/../scripts/layout.sh"  # root, conf, mem, tasks, tmp, here: the workspace or hat's state
py=""
for c in python3 python; do command -v "$c" >/dev/null 2>&1 && { py=$c; break; }; done
[ -z "$py" ] && command -v py >/dev/null 2>&1 && py="py -3"
[ -n "$py" ] || exit 0
if [ "${1:-}" = start ]; then
  $py "$here/scripts/session_handoff.py" start 2>/dev/null
else
  $py "$here/scripts/session_handoff.py" "${1:-end}" >/dev/null 2>&1
fi
exit 0
