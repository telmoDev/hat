# Sourced by the bash scripts and hooks: where a project's files are (layout.py for the Python ones).
# In a workspace with its own layer they are under the workspace root, as they always were. Under the global
# install HAT_STATE (the project's ~/.hat/projects/<id>/) and HAT_ROOT (the project root) are set, and the
# project's config, memory, task files and stamps live in HAT_STATE: nothing is written inside the project.
# Sets: root conf mem tasks tmp here (here = the folder holding scripts/ and hooks/), and git_wrapper, the path of
# GIT_WRAPPER once the conf is sourced: an absolute path as it is (hat moves a workspace's wrapper into its state),
# a relative one from the root.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Run by hand from the clone (no hook set HAT_STATE): find the project from the folder it runs in.
if [ -z "${HAT_STATE:-}" ] && [ "$(basename "$(dirname "$here")")" = templates ] && [ -f "$here/../../scripts/hat.py" ]; then
  _py=""; for _c in python3 python; do command -v "$_c" >/dev/null 2>&1 && { _py=$_c; break; }; done
  if [ -n "$_py" ] && _hit=$($_py "$here/../../scripts/hat.py" resolve-payload <<< '{}' 2>/dev/null); then
    IFS=$'\t' read -r HAT_PROJECT HAT_ROOT HAT_STATE <<< "$_hit"
    HAT_STATE=${HAT_STATE%$'\r'}
    export HAT_PROJECT HAT_ROOT HAT_STATE
  fi
fi
if [ -n "${HAT_STATE:-}" ]; then
  root="${HAT_ROOT:-$PWD}" conf="$HAT_STATE/config" mem="$HAT_STATE/memory" tasks="$HAT_STATE/tasks" tmp="$HAT_STATE/tmp"
else
  root="$(cd "$here/.." && pwd)"  # the workspace root, whichever tool runs this
  conf="$root/.orchestrator/orchestrator.conf" mem="$root/memory" tasks="$root/odd/tasks" tmp="$root/.orchestrator/tmp"
fi
git_wrapper() { case "${GIT_WRAPPER:-}" in /*|[A-Za-z]:[/\\]*) printf '%s' "$GIT_WRAPPER" ;; *) printf '%s' "$root/$GIT_WRAPPER" ;; esac; }
