#!/usr/bin/env bash
# Hook entry for the local telemetry: passes the hook's stdin to .orchestrator/scripts/telemetry.py <args>.
# Never fails the session and never prints (a SessionStart hook's output would become context): whatever goes
# wrong is noted in .orchestrator/telemetry/errors.log. TELEMETRY="off" in orchestrator.conf turns it off.
. "$(dirname "$0")/../scripts/layout.sh"  # root, conf, mem, tasks, tmp, here: the workspace or hat's state
[ -f "$conf" ] && . "$conf" >/dev/null 2>&1
[ "${TELEMETRY:-on}" = off ] && exit 0
export TEMPLATE_VERSION TELEMETRY_TRANSCRIPTS
py=""
for c in python3 python; do command -v "$c" >/dev/null 2>&1 && { py=$c; break; }; done
[ -z "$py" ] && command -v py >/dev/null 2>&1 && py="py -3"
if [ -z "$py" ]; then
  log="${HAT_STATE:-$root/.orchestrator/telemetry}"
  mkdir -p "$log" 2>/dev/null && echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) hook: Python 3 not found" >>"$log/errors.log" 2>/dev/null
  exit 0
fi
$py "$here/scripts/telemetry.py" "$@" >/dev/null 2>&1
exit 0
