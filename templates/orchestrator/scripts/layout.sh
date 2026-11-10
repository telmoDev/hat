# Sourced by the bash scripts and hooks: where a project's files are (layout.py for the Python ones).
# In a workspace with its own layer they are under the workspace root, as they always were. Under the global
# install HAT_STATE (the project's ~/.hat/projects/<id>/) and HAT_ROOT (the project root) are set, and the
# project's config, memory, task files and stamps live in HAT_STATE: nothing is written inside the project.
# Sets: root conf mem tasks tmp here (here = the folder holding scripts/ and hooks/).
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -n "${HAT_STATE:-}" ]; then
  root="${HAT_ROOT:-$PWD}" conf="$HAT_STATE/config" mem="$HAT_STATE/memory" tasks="$HAT_STATE/tasks" tmp="$HAT_STATE/tmp"
else
  root="$(cd "$here/.." && pwd)"  # the workspace root, whichever tool runs this
  conf="$root/.orchestrator/orchestrator.conf" mem="$root/memory" tasks="$root/odd/tasks" tmp="$root/.orchestrator/tmp"
fi
