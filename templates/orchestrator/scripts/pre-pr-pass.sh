#!/usr/bin/env bash
# Record that the pre-PR gate (.orchestrator/pre-pr-checklist.md) passed on a branch's current commit.
#   .orchestrator/scripts/pre-pr-pass.sh <repo> <branch>
# push-pr.sh refuses to push a branch whose HEAD is not the stamped commit, so any new commit needs a new gate.
# With TDD="strict" in orchestrator.conf it refuses a branch where a code commit (subject matching TDD_CODE_COMMIT)
# has no test commit (TDD_TEST_COMMIT) since the previous code commit on its own line of history (merges skipped;
# only commits since TDD_SINCE when set). TDD_EXEMPT="<reason>" skips that check for this branch and prints the reason. TDD_REPOS, when set,
# limits the check to those repos.
set -euo pipefail
. "$(dirname "$0")/layout.sh"  # root, conf, mem, tasks, tmp, here: the workspace or hat's state
. "$conf"
[ $# -eq 2 ] || { echo "usage: pre-pr-pass.sh <repo> <branch>" >&2; exit 2; }
repo=$1 branch=$2
case " $REPOS " in *" $repo "*) ;; *) echo "pre-pr-pass: repo must be one of: $REPOS" >&2; exit 2 ;; esac
sha=$(git -C "$root/$repo" rev-parse --verify "refs/heads/$branch")

if [ "${TDD:-off}" = strict ] && [ -n "${TDD_EXEMPT:-}" ]; then
  echo "pre-pr-pass: TDD check skipped: $TDD_EXEMPT"
elif [ "${TDD:-off}" = strict ] && { [ -z "${TDD_REPOS:-}" ] || case " $TDD_REPOS " in *" $repo "*) true ;; *) false ;; esac; }; then
  base=""; for kv in ${BASE_BRANCHES:-}; do [ "${kv%%=*}" = "$repo" ] && base=${kv#*=}; done
  [ -n "${TDD_TEST_COMMIT:-}" ] && [ -n "${TDD_CODE_COMMIT:-}" ] \
    || { echo "pre-pr-pass: TDD=\"strict\" needs TDD_TEST_COMMIT and TDD_CODE_COMMIT in orchestrator.conf" >&2; exit 1; }
  ref="origin/$base"; git -C "$root/$repo" rev-parse -q --verify "$ref" >/dev/null || ref=$base
  git -C "$root/$repo" rev-parse -q --verify "$ref" >/dev/null \
    || { echo "pre-pr-pass: no base branch for $repo in BASE_BRANCHES" >&2; exit 1; }
  # A bare date means its midnight: git alone reads "YYYY-MM-DD" as that day at the current time of day.
  since=(); case "${TDD_SINCE:-}" in "") ;; *:*) since=(--since="$TDD_SINCE") ;; *) since=(--since="$TDD_SINCE 00:00") ;; esac
  # Walk back from each code commit through its first parents, not the range as one line by date: a stacked branch
  # that merged its base back in would interleave the two branches' commits.
  untested=$(git -C "$root/$repo" log ${since[@]+"${since[@]}"} --format='%H%x09%P%x09%s' "$ref..$sha" \
    | TDD_TEST_COMMIT=$TDD_TEST_COMMIT TDD_CODE_COMMIT=$TDD_CODE_COMMIT awk -F'\t' '
      { np = split($2, p, " "); parent[$1] = p[1]; merge[$1] = np > 1; subj[$1] = $3; order[++n] = $1 }
      END {
        for (i = n; i >= 1; i--) {  # oldest first
          c = order[i]
          if (merge[c] || subj[c] !~ ENVIRON["TDD_CODE_COMMIT"]) continue
          tested = 0
          for (q = parent[c]; q in subj; q = parent[q]) {
            if (merge[q]) continue
            if (subj[q] ~ ENVIRON["TDD_TEST_COMMIT"]) { tested = 1; break }
            if (subj[q] ~ ENVIRON["TDD_CODE_COMMIT"]) break
          }
          if (!tested) { print substr(c, 1, 7) " \"" subj[c] "\""; exit }
        }
      }')
  [ -z "$untested" ] || { echo "pre-pr-pass: $untested has no test commit before it (TDD); see the checklist's *Test first* item (if it came from the base, fetch origin and re-run)" >&2; exit 1; }
fi
mkdir -p "$tmp/pre-pr"
echo "$sha" > "$tmp/pre-pr/${repo//\//_}--${branch//\//_}"
echo "pre-pr gate passed: $repo $branch $sha"
