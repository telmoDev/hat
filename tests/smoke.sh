#!/usr/bin/env bash
# Smoke test: scaffold a throwaway two-repo workspace, run the checks of SKILL.md step 4 on it, and exercise the
# gate scripts (pre-pr-pass.sh, push-pr.sh) against local bare origins and a stub gh. Touches nothing outside a
# temporary directory and ignores the user's git config.
#   bash tests/smoke.sh
# Runs on macOS, Linux and Windows (Git Bash), like the scaffold. CI runs it on all three.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
py=""; for c in python3 python "py -3"; do $c -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1 && { py=$c; break; }; done
[ -n "$py" ] || { echo "smoke: Python 3.8+ not found" >&2; exit 2; }

# Isolated git: no global or system config (signing, hooks, templates), a fixed identity and branch name.
printf '[user]\n\tname = smoke\n\temail = smoke@example.com\n[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n' >"$tmp/gitconfig"
export GIT_CONFIG_GLOBAL="$tmp/gitconfig" GIT_CONFIG_NOSYSTEM=1
# A stub gh: no open PRs, and "pr create" prints a URL.
mkdir -p "$tmp/bin"
cat >"$tmp/bin/gh" <<'EOF'
#!/usr/bin/env bash
case "${1:-} ${2:-}" in
  "pr create") echo https://example.invalid/pr/1 ;;
  "pr list") case " $* " in *" --jq "*) ;; *) echo '[]' ;; esac ;;
esac
EOF
chmod +x "$tmp/bin/gh"; export PATH="$tmp/bin:$PATH"

n=0
ok() { n=$((n+1)); echo "ok $n - $1"; }
die() { echo "not ok - $1" >&2; [ -f "$tmp/out" ] && sed 's/^/  | /' "$tmp/out" >&2; exit 1; }
run() { local d=$1; shift; "$@" >"$tmp/out" 2>&1 || die "$d"; ok "$d"; }
refuse() { # refuse <description> <expected message> <command...>: it must fail, saying that
  local d=$1 m=$2; shift 2
  if "$@" >"$tmp/out" 2>&1; then die "$d (it passed)"; fi
  grep -qF "$m" "$tmp/out" || die "$d (failed without '$m')"; ok "$d"
}

ws="$tmp/ws"
for r in api web; do
  git init -q "$ws/$r"; echo "# $r" >"$ws/$r/README.md"
  git -C "$ws/$r" add README.md; git -C "$ws/$r" commit -qm "chore: init"
  git init -q --bare "$tmp/origin/$r.git"
  git -C "$ws/$r" remote add origin "$tmp/origin/$r.git"; git -C "$ws/$r" push -q -u origin main
done

# Scaffold, then again: the second run creates nothing.
run "scaffold --git" bash "$here/scripts/scaffold.sh" --git "$ws"
grep -q '^create AGENTS.md$' "$tmp/out" && grep -q '^create .codex/agents/api-dev.toml$' "$tmp/out" || die "scaffold created the layer"
run "scaffold again" bash "$here/scripts/scaffold.sh" --git "$ws"
! grep -q '^create ' "$tmp/out" || die "a second scaffold creates nothing"
ok "a second scaffold creates nothing"
! grep -rIn '{{[A-Z_]*}}' "$ws/AGENTS.md" "$ws/CLAUDE.md" "$ws/.orchestrator" "$ws/.agents" "$ws/.claude" "$ws/.codex" "$ws/memory" >"$tmp/out" \
  || die "no placeholder left unrendered"
ok "no placeholder left unrendered"

# SKILL.md step 4.
cd "$ws"
for f in .orchestrator/scripts/*.sh .orchestrator/hooks/*.sh; do bash -n "$f" || die "bash -n $f"; done; ok "scripts parse"
run "memory-check.py compiles" $py -m py_compile .orchestrator/scripts/memory-check.py
run "telemetry.py compiles" $py -m py_compile .orchestrator/scripts/telemetry.py
run "telemetry unit tests" $py -m unittest discover -s "$here/tests"
run "skill copies in sync" bash .orchestrator/scripts/sync-skills.sh --check
if $py -c 'import tomllib' 2>/dev/null; then
  run "Codex TOML parses" $py -c "import tomllib,sys; [tomllib.load(open(f,'rb')) for f in sys.argv[1:]]" .codex/*.toml .codex/agents/*.toml
else echo "skip - Codex TOML (Python < 3.11, no tomllib)"; fi
if command -v node >/dev/null; then
  { echo '(async () => {'; sed 's/^export //' .claude/workflows/pre-pr-review.js; echo '})'; } >"$tmp/wf.js"
  run "workflow parses" node --check "$tmp/wf.js"
else echo "skip - workflow (no node)"; fi
run "memory-state.sh" bash .orchestrator/scripts/memory-state.sh
run "memory-check.py" $py .orchestrator/scripts/memory-check.py

# ODD: both tools get the same rules, and memory-check covers the task files.
[ -f odd/README.md ] || die "scaffold created odd/README.md"; ok "scaffold created odd/README.md"
grep -qx '@AGENTS.md' CLAUDE.md || die "CLAUDE.md imports AGENTS.md"; ok "Claude Code reads the guide Codex reads"
for rule in 'Organic Driven Development (ODD)' '**Ask or change.**' '**Size.**' 'odd/tasks/<feature>.md' '**Resume.**' 'ask the user once per feature'; do
  grep -qF "$rule" AGENTS.md || die "AGENTS.md has the ODD rule '$rule'"
done; ok "AGENTS.md has the ODD rules (ask or change, size, task file, resume, push)"
for a in api-dev architect; do
  grep -q 'odd/tasks/' ".claude/agents/$a.md" && grep -q 'odd/tasks/' ".codex/agents/$a.toml" || die "$a reads the task file in both tools"
done; ok "the agents read the task file in both tools"
mkdir -p odd/tasks; cp memory/PROGRESS.md memory/PROJECT_STATE.md .codex/config.toml "$tmp/"
cat >odd/tasks/login.md <<'EOF'
# login

Status: active · Next: T2

## Request
> Add a login.

## Outcome
Criteria: O1 the form posts · O2 the session persists

## Tasks
| ID | Task | Serves | Status |
|---|---|---|---|
| T1 | form | O1 | done |
| T2 | session | O2 | pending |

## Evidence
- 2026-01-01 T1 · O1 · `npm test form` → passed: 3 passing
EOF
printf '\n## 2026-01-01 — login (—) — partial\nDoc: odd/tasks/login.md\nContinue at: api, T2\n' >>memory/PROGRESS.md
perl -0pi -e 's/(\| Feature \|.*\n\|---[|-]*\n)/$1| login | — | odd\/tasks\/login.md | — | 1\/2 passed | in progress | not run |\n/' memory/PROJECT_STATE.md
mc() { $py .orchestrator/scripts/memory-check.py; }
run "memory-check accepts a task file that agrees with the memory" mc
cp odd/tasks/login.md "$tmp/login.md"
echo 'token: abcd1234efgh' >>odd/tasks/login.md
refuse "memory-check refuses a secret in a task file" "looks like a secret" mc
cp "$tmp/login.md" odd/tasks/login.md; sed -i.bak 's/| O2 | pending |/| O2 | done |/' odd/tasks/login.md
refuse "memory-check refuses a done task with no evidence" "T2 is done with no evidence" mc
cp "$tmp/login.md" odd/tasks/login.md; sed -i.bak 's#1/2 passed#2/2 passed#' memory/PROJECT_STATE.md
refuse "memory-check refuses an In flight outcome the task file contradicts" "the task file has 1/2 passed" mc
cp "$tmp/PROJECT_STATE.md" memory/PROJECT_STATE.md; sed -i.bak 's/^Status: active/Status: done/' odd/tasks/login.md
refuse "memory-check refuses a done task file still in PROGRESS" "is done but PROGRESS still lists it" mc
cp "$tmp/login.md" odd/tasks/login.md; sed -i.bak 's#odd/tasks/login.md#odd/tasks/gone.md#' memory/PROGRESS.md
refuse "memory-check refuses a link to a missing task file" "no such task file" mc
cp "$tmp/PROGRESS.md" memory/PROGRESS.md
grep -q '^project_doc_max_bytes = ' .codex/config.toml || die "Codex config sets project_doc_max_bytes"
[ "$(wc -c <AGENTS.md)" -le "$(sed -n 's/^project_doc_max_bytes = //p' .codex/config.toml)" ] || die "AGENTS.md fits Codex's limit"
ok "AGENTS.md fits Codex's project_doc_max_bytes"
sed -i.bak 's/^project_doc_max_bytes = .*/project_doc_max_bytes = 1000/' .codex/config.toml
refuse "memory-check refuses an AGENTS.md that Codex would truncate" "Codex reads only" mc
cp "$tmp/config.toml" .codex/config.toml; rm -rf odd/tasks memory/*.bak .codex/*.bak

# The gate. TDD is strict by default: a code commit needs a test commit before it.
api="$ws/api"
commit() { echo "$1" >>"$api/x.txt"; git -C "$api" add x.txt; git -C "$api" commit -qm "$1"; }
git -C "$api" checkout -qb feat/untested; commit "feat: untested"
refuse "pre-pr-pass refuses a code commit with no test before it" "has no test commit before it" bash .orchestrator/scripts/pre-pr-pass.sh api feat/untested
git -C "$api" checkout -q main; git -C "$api" checkout -qb feat/x
commit "test: x"; commit "feat: x"$'\n\nCo-authored-by: Ana <ana@example.com>'
run "pre-pr-pass stamps a tested branch" bash .orchestrator/scripts/pre-pr-pass.sh api feat/x

sed -i.bak 's/^ATTRIBUTION=""/ATTRIBUTION="refuse"/' .orchestrator/orchestrator.conf
printf 'Why: smoke.\n\nCo-authored-by: Ana <ana@example.com>\n' >"$tmp/body.md"
printf 'Why: smoke.\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)\n' >"$tmp/body-ai.md"
refuse "push-pr refuses an AI-attributed body" "body carries AI attribution" bash .orchestrator/scripts/push-pr.sh api feat/x main "feat: x" "$tmp/body-ai.md"
run "push-pr pushes with a person as co-author" bash .orchestrator/scripts/push-pr.sh api feat/x main "feat: x" "$tmp/body.md"
grep -q example.invalid "$tmp/out" || die "push-pr opened the PR"

commit "fix: after the gate"
refuse "push-pr refuses an unstamped HEAD" "gate has not passed" bash .orchestrator/scripts/push-pr.sh api feat/x main "feat: x" "$tmp/body.md"
git -C "$api" checkout -q main; git -C "$api" checkout -qb feat/ai
commit "test: ai"; commit "feat: ai"$'\n\nCo-Authored-By: Claude Opus <noreply@anthropic.com>'
run "pre-pr-pass stamps the AI-attributed branch" bash .orchestrator/scripts/pre-pr-pass.sh api feat/ai
refuse "push-pr refuses an AI-attributed commit" "carries AI attribution" bash .orchestrator/scripts/push-pr.sh api feat/ai main "feat: ai" "$tmp/body.md"
refuse "push-pr refuses the base branch" "refusing to push the base branch" bash .orchestrator/scripts/push-pr.sh api main main "feat: x" "$tmp/body.md"

echo "smoke: $n checks passed"
