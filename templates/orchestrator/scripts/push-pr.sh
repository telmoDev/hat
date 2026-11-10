#!/usr/bin/env bash
# Push a branch an agent committed locally and open its pull request, in one deterministic step.
#   .orchestrator/scripts/push-pr.sh <repo> <branch> <base> <title> <body-file> [--draft] [--reviewer <login>]
# Refuses (AGENTS.md flow step 4, .orchestrator/pre-pr-checklist.md): a push to a base branch, a branch that does
# not contain origin/<base>, and a HEAD the pre-PR gate has not stamped (pre-pr-pass.sh). And what orchestrator.conf
# sets: a body without TICKET_LINE, a title not matching TITLE_PATTERN or over TITLE_MAX characters, and, with
# ATTRIBUTION="refuse", AI attribution in the body or the commits.
# Git runs through GIT_WRAPPER when orchestrator.conf sets one. If the branch already has an open PR, it only
# pushes and prints that PR's URL. It never merges and never force-pushes.
set -euo pipefail
. "$(dirname "$0")/layout.sh"  # root, conf, mem, tasks, tmp, here: the workspace or hat's state
. "$conf"
usage="usage: push-pr.sh <repo> <branch> <base> <title> <body-file> [--draft] [--reviewer <login>]"
[ $# -ge 5 ] || { echo "$usage" >&2; exit 2; }
repo=$1 branch=$2 base=$3 title=$4 body=$5; shift 5
extra=()
while [ $# -gt 0 ]; do
  case "$1" in
    --draft) extra+=(--draft); shift ;;
    --reviewer) extra+=(--reviewer "${2:?--reviewer needs a login}"); shift 2 ;;
    *) echo "$usage" >&2; exit 2 ;;
  esac
done

fail() { echo "push-pr: $*" >&2; exit 1; }
rgit() { if [ -n "${GIT_WRAPPER:-}" ]; then bash "$root/$GIT_WRAPPER" "$repo" "$@"; else git -C "$root/$repo" "$@"; fi; }
case " $REPOS " in *" $repo "*) ;; *) fail "repo must be one of: $REPOS" ;; esac
for kv in ${BASE_BRANCHES:-}; do [ "${kv%%=*}" = "$repo" ] && [ "${kv#*=}" = "$branch" ] && fail "refusing to push the base branch $branch"; done
case "$branch" in main|master) fail "refusing to push $branch" ;; esac
[ -f "$body" ] || fail "body file not found: $body"
[ -z "${TICKET_LINE:-}" ] || grep -Eq "$TICKET_LINE" "$body" || fail "body has no line matching $TICKET_LINE"
refuse_ai=no; [ "${ATTRIBUTION:-}" = refuse ] && refuse_ai=yes
# AI attribution only: a Co-authored-by trailer naming a person is fine.
ai='(claude|codex|copilot|cursor|gemini|chatgpt|openai|anthropic)'
ai_re="co-authored-by:.*$ai|generated (with|by) \\[?$ai|claude\\.ai/code|🤖"
[ $refuse_ai = yes ] && grep -Eiq "$ai_re" "$body" && fail "body carries AI attribution"
git -C "$root/$repo" rev-parse --verify -q "refs/heads/$branch" >/dev/null || fail "no local branch $branch in $repo"
[ -z "${TITLE_MAX:-}" ] || [ ${#title} -le "$TITLE_MAX" ] || fail "title is ${#title} characters, over $TITLE_MAX"
[ -z "${TITLE_PATTERN:-}" ] || printf '%s\n' "$title" | grep -Eq "$TITLE_PATTERN" || fail "title does not match TITLE_PATTERN ($TITLE_PATTERN)"

rgit fetch -q origin "$base"
[ $refuse_ai = yes ] && git -C "$root/$repo" log --format=%B "origin/$base..$branch" | grep -Eiq "$ai_re" \
  && fail "a commit on $branch carries AI attribution"
git -C "$root/$repo" merge-base --is-ancestor "origin/$base" "$branch" \
  || fail "$branch does not contain origin/$base: bring the base in and re-run the gate"
stamp="$tmp/pre-pr/${repo//\//_}--${branch//\//_}"
head=$(git -C "$root/$repo" rev-parse "refs/heads/$branch")
[ -f "$stamp" ] && [ "$(cat "$stamp")" = "$head" ] \
  || fail "the pre-PR gate has not passed on $branch at ${head:0:7} (.orchestrator/pre-pr-checklist.md, then pre-pr-pass.sh)"

rgit push -u origin "$branch"

cd "$root/$repo"
existing=$(gh pr list --head "$branch" --state open --json url --jq '.[0].url // empty')
if [ -n "$existing" ]; then echo "$existing"; exit 0; fi
gh pr create --base "$base" --head "$branch" --title "$title" --body-file "$body" ${extra[@]+"${extra[@]}"}
