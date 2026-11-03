#!/usr/bin/env bash
# Scaffold the orchestrator layer into a workspace root, for Claude Code, Codex or both.
#   bash scaffold.sh --git|--no-git [--no-update-check] [--tools claude,codex] <workspace-root> [repo ...]
# Shared: AGENTS.md, memory/, odd/ (task files), .orchestrator/ (config, checklist, scripts, hooks), .agents/skills/.
# Claude Code: CLAUDE.md (imports AGENTS.md), .claude/ (settings, agents, workflow, copies of the skills).
# Codex: .codex/ (config.toml, hooks.json, agents/*.toml rendered from the same agent sources).
# --git:    version the orchestration layer (git init at the root when it has subrepos, a root .gitignore).
# --no-git: don't version it (no git init, no .gitignore at the root; in single-repo mode its files go to
#           .git/info/exclude instead of being committed). One of the two is required: it is the user's call.
# --no-update-check: UPDATE_CHECK="off" (no notice at session start when an orchestrator update is out).
# Repos default to the immediate subdirectories holding .git; if none, the root itself (".").
# A repo name with whitespace is refused. Agent names are the repo name slugged (My.API -> my-api-dev).
# Each repo's base branch (origin/HEAD, else main, else master) goes to BASE_BRANCHES in orchestrator.conf.
# Codex models per tier default to CODEX_TRIVIAL / CODEX_NORMAL / CODEX_HARD from the environment.
# Runs on macOS, Linux and Windows (Git Bash). Creates no symlinks. Never overwrites: an existing file is "skip".
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
tpl="$here/templates"
root_git="" tools="claude,codex" update_check=on
while [ $# -gt 0 ]; do
  case "$1" in
    --git) root_git=yes; shift ;;
    --no-git) root_git=no; shift ;;
    --no-update-check) update_check=off; shift ;;
    --tools) tools="${2:?--tools needs claude, codex or claude,codex}"; shift 2 ;;
    *) break ;;
  esac
done
[ -n "$root_git" ] || { echo "scaffold: pass --git or --no-git: whether to version the orchestration layer is the user's call" >&2; exit 2; }
case ",$tools," in *,claude,*|*,codex,*) ;; *) echo "scaffold: --tools takes claude, codex or both" >&2; exit 2 ;; esac
has() { case ",$tools," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }
root="$(cd "${1:?usage: scaffold.sh --git|--no-git [--tools claude,codex] <workspace-root> [repo ...]}" && pwd)"; shift
# The path written into the guides: on Windows (Git Bash) the native C:/... form, which every tool understands.
root_shown=$(cd "$root" && { pwd -W 2>/dev/null || pwd; })
codex_trivial="${CODEX_TRIVIAL:-gpt-6-luna}" codex_normal="${CODEX_NORMAL:-gpt-6.1-sol}" codex_hard="${CODEX_HARD:-gpt-6-astra}"
version=$(cat "$here/VERSION" 2>/dev/null || echo unreleased)
py=""; for c in python3 python "py -3"; do $c -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1 && { py=$c; break; }; done
[ -n "$py" ] || { echo "scaffold: Python 3.8+ not found (python3, python or py -3)" >&2; exit 2; }

if [ $# -gt 0 ]; then
  repos=("$@")
else
  repos=()
  for d in "$root"/*/; do [ -e "$d.git" ] && repos+=("$(basename "$d")"); done
  [ ${#repos[@]} -gt 0 ] || repos=(".")
fi
for r in "${repos[@]}"; do
  [ -d "$root/$r" ] || { echo "scaffold: no directory $root/$r" >&2; exit 2; }
  case "$r" in *[[:space:]]*) echo "scaffold: repo name '$r' has whitespace; rename the directory first" >&2; exit 2 ;; esac
done

agent_of() { # the developer agent's name: lowercase letters, digits and hyphens only
  [ "$1" = "." ] && { echo dev; return; }
  local s; s=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -e 's/[^a-z0-9-]/-/g' -e 's/--*/-/g' -e 's/^-//' -e 's/-$//')
  echo "${s:-repo}-dev"
}
base_of() { # the repo's base branch, or empty when none can be found
  local d="$root/$1" b
  git -C "$d" rev-parse --git-dir >/dev/null 2>&1 || return 0
  b=$(git -C "$d" symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null) && { echo "${b#origin/}"; return; }
  for b in main master; do git -C "$d" rev-parse -q --verify "refs/heads/$b" >/dev/null && { echo "$b"; return; }; done
  return 0
}
agents=" "; bases=""
for r in "${repos[@]}"; do
  a=$(agent_of "$r")
  case "$agents" in *" $a "*) echo "scaffold: two repos map to the agent name '$a'; rename one directory" >&2; exit 2 ;; esac
  agents+="$a "
  b=$(base_of "$r"); bases+="$r=${b:-TODO(orchestrator-setup)} "
done
bases="${bases% }"
base_for() { local kv; for kv in $bases; do [ "${kv%%=*}" = "$1" ] && { echo "${kv#*=}"; return; }; done; return 0; }

name="$(basename "$root")"
repo_list="${repos[*]}"
repo_rows=""; dev_rows=""; repo_sections=""
guide_of() { # the guide a repo's agent reads: its own CLAUDE.md/AGENTS.md, or its section at the root
  local r=$1
  for g in AGENTS.md CLAUDE.md; do
    [ "$r" != "." ] && [ -f "$root/$r/$g" ] && { echo "\`$root_shown/$r/$g\`"; return; }
  done
  echo "its section under *Repo guides* in \`$root_shown/AGENTS.md\` (it has no guide of its own)"
}
for r in "${repos[@]}"; do
  label=$([ "$r" = "." ] && echo "$name (root)" || echo "$r")
  agent=$(agent_of "$r")
  if [ "$r" != "." ] && { [ -f "$root/$r/CLAUDE.md" ] || [ -f "$root/$r/AGENTS.md" ]; }; then
    own=$([ -f "$root/$r/AGENTS.md" ] && echo AGENTS.md || echo CLAUDE.md)
    guide="\`$r/$own\`"
  else
    guide="*Repo guides* › \`$label\` below"
    repo_sections+="### \`$label\`"$'\n\n'"- Stack: TODO(orchestrator-setup)"$'\n'"- Layout: TODO(orchestrator-setup): where the main code, the tests and the config live"$'\n'"- Conventions: TODO(orchestrator-setup): naming, error handling, commits and PR titles (only what the code and the history show)"$'\n'"- Checks: TODO(orchestrator-setup): the test command and the other local checks"$'\n'
  fi
  repo_rows+="| \`$label\` | TODO(orchestrator-setup): stack | \`$(base_for "$r")\` | $guide |"$'\n'
  dev_rows+="| \`$agent\` | normal (by tier) | implementation in \`$label\` |"$'\n'
done
[ -n "$repo_sections" ] || repo_sections="All repos have their own guide."$'\n'
layer="\`AGENTS.md\`, \`CLAUDE.md\`, \`.orchestrator/\`, \`.agents/\`, \`.claude/\`, \`.codex/\`, \`memory/\`, \`odd/\`"
if [ "$root_git" = yes ]; then
  root_vcs="The root is its own small git repo. It ignores the app repos and versions only the orchestration layer ($layer)."
else
  root_vcs="The orchestration layer ($layer) is not versioned: never run git at the root and never commit it to a repo."
fi

created=(); skipped=()
render() { # render <template> <dest> [repo]
  local src=$1 dest=$2 repo=${3:-}
  if [ -e "$dest" ] || [ -L "$dest" ]; then skipped+=("${dest#$root/}"); return 1; fi
  mkdir -p "$(dirname "$dest")"
  local guide="" agent="" base=""
  [ -n "$repo" ] && { guide="$(guide_of "$repo")"; agent="$(agent_of "$repo")"; base="$(base_for "$repo")"; }
  ROOT="$root_shown" NAME="$name" REPOS="$repo_list" REPO="$repo" REPO_GUIDE="$guide" AGENT="$agent" BASE="$base" BASES="$bases" \
  REPO_ROWS="$repo_rows" DEV_ROWS="$dev_rows" REPO_SECTIONS="$repo_sections" DATE="$(date +%F)" \
  ROOT_GIT="$root_git" ROOT_VCS="$root_vcs" CODEX_TRIVIAL="$codex_trivial" CODEX_NORMAL="$codex_normal" CODEX_HARD="$codex_hard" VERSION="$version" UPDATE_CHECK="$update_check" \
    perl -pe 's/\{\{(ROOT|NAME|REPOS|REPO_GUIDE|REPO_SECTIONS|REPO_ROWS|DEV_ROWS|REPO|AGENT|BASES|BASE|DATE|ROOT_GIT|ROOT_VCS|CODEX_TRIVIAL|CODEX_NORMAL|CODEX_HARD|VERSION|UPDATE_CHECK)\}\}/$ENV{$1}/g' "$src" >"$dest"
  case "$dest" in *.sh|*.py) chmod +x "$dest" ;; esac
  created+=("${dest#$root/}")
}
guide() { # guide <template> <name> <aside>: the root guide, or an aside to merge by hand when one exists
  if [ -e "$root/$2" ] && grep -q 'Tool mapping' "$root/$2"; then
    skipped+=("$2 (already the orchestrator's)")
  elif [ -e "$root/$2" ]; then
    render "$1" "$root/$3" || true
    echo "note: $2 exists; merge $3 into it by hand"
  else
    render "$1" "$root/$2" || true
  fi
}

# Shared layer.
guide "$tpl/AGENTS.md" AGENTS.md .orchestrator/AGENTS.orchestrator.md
if [ "$root_git" = yes ]; then render "$tpl/gitignore" "$root/.gitignore" || true; fi
render "$tpl/gitattributes" "$root/.gitattributes" || true
for f in "$tpl"/memory/*.md; do render "$f" "$root/memory/$(basename "$f")" || true; done
render "$tpl/odd/README.md" "$root/odd/README.md" || true
render "$tpl/orchestrator/orchestrator.conf" "$root/.orchestrator/orchestrator.conf" || true
render "$tpl/orchestrator/pre-pr-checklist.md" "$root/.orchestrator/pre-pr-checklist.md" || true
render "$tpl/orchestrator/rates.json" "$root/.orchestrator/rates.json" || true
for f in "$tpl"/orchestrator/scripts/* "$tpl"/orchestrator/hooks/*; do
  [ -f "$f" ] || continue  # e.g. a __pycache__ left by a local py_compile
  rel=${f#$tpl/orchestrator/}; render "$f" "$root/.orchestrator/$rel" || true
done
for d in "$tpl"/skills/*/; do s=$(basename "$d"); render "$d/SKILL.md" "$root/.agents/skills/$s/SKILL.md" || true; done

# Agents: rendered once as Claude Code definitions, the source the Codex ones are generated from.
agent_src="$root/.claude/agents"
if ! has claude; then agent_src=$(mktemp -d); fi
if [ -L "$root/.claude/agents" ]; then
  skipped+=(".claude/agents (symlink, left as is)")
else
  render "$tpl/agents/explorer.md" "$agent_src/explorer.md" || true
  render "$tpl/agents/architect.md" "$agent_src/architect.md" || true
  for r in "${repos[@]}"; do render "$tpl/agents/developer.md" "$agent_src/$(agent_of "$r").md" "$r" || true; done
fi

if has claude; then
  guide "$tpl/CLAUDE.md" CLAUDE.md .claude/CLAUDE.orchestrator.md
  render "$tpl/claude/settings.json" "$root/.claude/settings.json" || true
  render "$tpl/claude/workflows/pre-pr-review.js" "$root/.claude/workflows/pre-pr-review.js" || true
  copied=$(bash "$root/.orchestrator/scripts/sync-skills.sh")
  [ -z "$copied" ] || created+=(".claude/skills/ (copies of .agents/skills/)")
fi
if has codex; then
  render "$tpl/codex/config.toml" "$root/.codex/config.toml" || true
  render "$tpl/codex/hooks.json" "$root/.codex/hooks.json" || true
  for md in "$agent_src"/*.md; do
    [ -e "$md" ] || continue
    out="$root/.codex/agents/$(basename "${md%.md}").toml"
    if [ -e "$out" ]; then skipped+=("${out#$root/}"); continue; fi
    mkdir -p "$(dirname "$out")"; $py "$here/scripts/agent-to-codex.py" "$md" "$out" "$codex_trivial"; created+=("${out#$root/}")
  done
fi
has claude || rm -rf "$agent_src"

# The root versions only the orchestration layer: ignore each subrepo.
if [ "$root_git" = no ]; then
  # Single-repo mode: keep the unversioned layer out of the repo's status, locally only.
  if [ "$repo_list" = "." ] && [ -d "$root/.git" ]; then
    ex="$root/.git/info/exclude"; mkdir -p "$(dirname "$ex")"; touch "$ex"
    for f in "${created[@]+"${created[@]}"}"; do grep -qxF "/${f%% *}" "$ex" || echo "/${f%% *}" >>"$ex"; done
    grep -qxF "/odd/" "$ex" || echo "/odd/" >>"$ex"  # the task files written later
    grep -qxF "/.orchestrator/telemetry/" "$ex" || echo "/.orchestrator/telemetry/" >>"$ex"  # the local telemetry store
    echo "excluded the new orchestration files in .git/info/exclude"
  fi
elif [ "$repo_list" != "." ] && [ -f "$root/.gitignore" ]; then
  for r in "${repos[@]}"; do grep -qxF "/$r/" "$root/.gitignore" || echo "/$r/" >>"$root/.gitignore"; done
  [ -d "$root/.git" ] || { git -C "$root" init -q && echo "git init at $root"; }
fi

echo "orchestrator-setup $version"
echo "tools: $tools"
echo "repos: $repo_list"
echo "base branches: $bases"
has codex && echo "codex models: trivial=$codex_trivial normal=$codex_normal hard=$codex_hard"
for f in "${created[@]+"${created[@]}"}"; do echo "create $f"; done
for f in "${skipped[@]+"${skipped[@]}"}"; do echo "skip   $f"; done
echo "next: replace every TODO(orchestrator-setup) marker (grep -rn 'TODO(orchestrator-setup)' AGENTS.md .orchestrator .agents .claude .codex)"
