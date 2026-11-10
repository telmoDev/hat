#!/usr/bin/env bash
# SessionStart: one line per ADR and decision-log entry in force, so the session knows what is binding
# without loading the docs. Paths come from ADR_DIR and DECISION_LOG in .orchestrator/orchestrator.conf; with
# neither set it prints nothing. Superseded, rejected and deprecated entries are left out; partly
# superseded ones are marked.
. "$(dirname "$0")/../scripts/layout.sh"  # root, conf, mem, tasks, tmp, here: the workspace or hat's state
[ -f "$conf" ] || exit 0
. "$conf"
adr="${ADR_DIR:+$root/$ADR_DIR}"; dl="${DECISION_LOG:+$root/$DECISION_LOG}"
{ [ -n "$adr" ] && [ -d "$adr" ]; } || { [ -n "$dl" ] && [ -f "$dl" ]; } || exit 0
skip='^(Superseded|Rejected|Deprecated)'
text=$(
  echo "Binding decisions in force. Open the file before relying on or contradicting one."
  if [ -n "$adr" ] && [ -d "$adr" ]; then
    for f in "$adr"/*.md; do
      [ -f "$f" ] || continue
      awk -v skip="$skip" '
        !t && /^# / { t=$0; sub(/^# /,"",t) }
        st=="" && /^\*\*Status:\*\*/ { st=$0; sub(/^\*\*Status:\*\* */,"",st) }
        st=="" && /^## Status/ { while ((getline l) > 0) if (l != "") { st=l; break } }
        END {
          if (!t || st ~ skip) exit
          printf "- %s%s\n", t, (tolower(st) ~ /superseded/ ? " (partly superseded)" : "")
        }' "$f"
    done
  fi
  if [ -n "$dl" ] && [ -f "$dl" ]; then
    awk -v skip="$skip" '
      /^## / { t=$0; sub(/^## /,"",t); want=1; next }
      want && /^\*\*Status:\*\*/ {
        s=$0; sub(/^\*\*Status:\*\* */,"",s); want=0
        if (s ~ skip) next
        printf "- %s%s\n", t, (tolower(s) ~ /superseded/ ? " (partly superseded)" : "")
      }' "$dl"
  fi
)
if command -v jq >/dev/null 2>&1; then
  printf '%s' "$text" | jq -Rs '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:.}}'
else
  printf '%s\n' "$text"
fi
