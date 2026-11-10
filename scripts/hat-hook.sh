#!/usr/bin/env bash
# The global install's one hook entry: bash <hat>/scripts/hat-hook.sh <hook> [args] < the hook's JSON.
# Finds the project from the payload's "cwd" (hat resolve). Outside a registered project, or in one that still has
# its own per-project layer (.orchestrator/, which runs its own hooks), it does nothing, except that the session
# start (<hook> = context) gets one line offering to register, migrate or clean up. Otherwise it sets
# HAT_PROJECT, HAT_ROOT and HAT_STATE and passes the payload to templates/orchestrator/hooks/<hook>.sh, or prints
# the session-start header for <hook> = context. Never fails the session.
hat="$(cd "$(dirname "$0")/.." && pwd)"  # the clone
input=$(cat)
py=""
for c in python3 python; do command -v "$c" >/dev/null 2>&1 && { py=$c; break; }; done
[ -z "$py" ] && command -v py >/dev/null 2>&1 && py="py -3"
[ -n "$py" ] || exit 0
hook="${1:-}"; shift 2>/dev/null
case "$hook" in context|telemetry|session-handoff|session-memory|decision-index) ;; *) exit 0 ;; esac
offer() { [ "$hook" = context ] && printf '%s' "$input" | $py "$hat/scripts/hat.py" offer-payload 2>/dev/null; exit 0; }
line=$(printf '%s' "$input" | $py "$hat/scripts/hat.py" resolve-payload 2>/dev/null) || offer
IFS=$'\t' read -r id root state <<< "$line"
state=${state%$'\r'}  # Python on Windows ends its lines with CRLF
[ -n "$state" ] || exit 0
[ -d "$root/.orchestrator" ] && offer
export HAT_PROJECT="$id" HAT_ROOT="$root" HAT_STATE="$state"
if [ "$hook" = context ]; then
  $py "$hat/scripts/hat.py" context "$root" 2>/dev/null
else
  printf '%s' "$input" | bash "$hat/templates/orchestrator/hooks/$hook.sh" "$@" 2>/dev/null
fi
exit 0
