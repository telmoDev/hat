#!/usr/bin/env bash
# Update a workspace set up with this skill (v0.1.0 or later) to its templates, keeping what the user changed.
#   bash update.sh [--dry-run] [--dev] <workspace-root>
# Plans everything before the first write; a user-changed script is kept and gets <file>.new; settings.json and
# orchestrator.conf only gain what they lack; text files (AGENTS.md, memory/, task files) are never edited, and
# the CHANGELOG's Workspaces steps to apply by hand are printed. Never deletes, never commits. Details: update.py.
# Runs on macOS, Linux and Windows (Git Bash).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
py=""; for c in python3 python "py -3"; do $c -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1 && { py=$c; break; }; done
[ -n "$py" ] || { echo "update: Python 3.8+ not found (python3, python or py -3)" >&2; exit 2; }
exec $py "$here/update.py" "$@"
