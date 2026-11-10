"""Where a project's files are, for every script (G2, docs/meta-harness/global-install.md).
In a workspace with its own layer they are under the workspace root, as they always were. Under the global install
the hook sets HAT_STATE (the project's ~/.hat/projects/<id>/), HAT_ROOT (the project root) and HAT_PROJECT (its
id): the project's config, memory, task files, telemetry and handoff state are then read and written there, and
nothing is written inside the project. layout.sh is the same for the bash scripts.
"""
import collections
import os

Layout = collections.namedtuple("Layout", "root conf memory tasks telemetry handoff tmp project task_prefix")


def root(script):
    """The project root: HAT_ROOT under the global install, else the workspace this script was copied into."""
    if os.environ.get("HAT_STATE"):
        return os.path.abspath(os.environ.get("HAT_ROOT") or os.getcwd())
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(script))))


def of(root):
    """The paths of the project at root. task_prefix is how the memory links a task file."""
    state = os.environ.get("HAT_STATE")
    if state:
        return Layout(root, os.path.join(state, "config"), os.path.join(state, "memory"),
                      os.path.join(state, "tasks"), os.path.join(state, "telemetry.db"),
                      os.path.join(state, "handoff"), os.path.join(state, "tmp"),
                      os.environ.get("HAT_PROJECT") or os.path.basename(root), "tasks/")
    ws = os.path.join(root, ".orchestrator")
    return Layout(root, os.path.join(ws, "orchestrator.conf"), os.path.join(root, "memory"),
                  os.path.join(root, "odd", "tasks"), os.path.join(ws, "telemetry", "telemetry.db"),
                  os.path.join(ws, "tmp", "handoff"), os.path.join(ws, "tmp"), os.path.basename(root), "odd/tasks/")
