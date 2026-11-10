#!/usr/bin/env python3
"""The harness capability contract: what each runtime (Claude Code, Codex) can really do for hat, and whether it is
installed and wired in this workspace.
  python3 .orchestrator/scripts/harness.py doctor [--json]
Capabilities are declared, not assumed: a runtime claims `verified` only for what was checked against its real
behaviour (docs/harnesses.md says how). Callers check a capability before using it; there is no forced parity.
The health check runs `<cli> --version` and reads the workspace's config files: no network, no model calls, and it
never starts a session.
"""
import json
import os
import re
import shutil
import subprocess
import sys

CAPABILITIES = ("health_check", "collect_events", "usage", "execute", "status", "cancel")
STATUSES = ("verified", "unverified", "unsupported")

ADAPTERS = {
    "claude-code": {
        "cli": "claude",
        "config": ".claude/settings.json",
        "hooks": [  # (event, script, argument): what hat needs in the settings
            ("SessionStart", "decision-index.sh", None), ("SessionStart", "update-check.sh", None),
            ("SessionStart", "telemetry.sh", "hook claude"), ("SessionStart", "session-handoff.sh", "start"),
            ("SessionEnd", "telemetry.sh", "hook claude"), ("SessionEnd", "session-handoff.sh", "end"),
            ("SubagentStart", "telemetry.sh", "hook claude"), ("SubagentStop", "telemetry.sh", "hook claude"),
            ("PostToolUse", "telemetry.sh", "hook claude"), ("PostToolUseFailure", "telemetry.sh", "hook claude"),
        ],
        "capabilities": {
            "health_check": ("verified", "`claude --version` and the hooks in `.claude/settings.json`"),
            "collect_events": ("verified", "six hooks into `telemetry.py hook claude` (docs/telemetry.md)"),
            "usage": ("verified", "transcript parser `claude-transcript/2`; `unavailable` on any unknown shape"),
            "execute": ("unverified", "`claude -p` exists; hat starts no sessions until opt-in dispatch (phase 7)"),
            "status": ("unsupported", "no session status interface; process-level once hat starts runs"),
            "cancel": ("unsupported", "no cancel interface; process-level once hat starts runs"),
        },
    },
    "codex": {
        "cli": "codex",
        "config": ".codex/hooks.json",
        "hooks": [
            ("SessionStart", "session-memory.sh", None), ("SessionStart", "decision-index.sh", None),
            ("SessionStart", "update-check.sh", None), ("SessionStart", "session-handoff.sh", "start"),
        ],
        "capabilities": {
            "health_check": ("unverified", "`codex --version` and `.codex/hooks.json`; not run against a real install"),
            "collect_events": ("unverified", "SessionStart hooks only (memory, decisions, update, handoff); "
                                             "no telemetry until real payloads are verified"),
            "usage": ("unverified", "no verified source: not recorded"),
            "execute": ("unverified", "`codex exec` exists; hat starts no sessions until opt-in dispatch (phase 7)"),
            "status": ("unsupported", "no session status interface known"),
            "cancel": ("unsupported", "no cancel interface known"),
        },
    },
}


def _has(command, script, arg):
    return re.search(re.escape(script) + '"?' + (r"\s+" + re.escape(arg) if arg else r"(\s|$)"), command) is not None


def health_check(runtime, root, env=None):
    """{installed, version, configured, missing}. Never raises for a missing tool or a broken config."""
    a = ADAPTERS[runtime]
    env = env or os.environ
    out = {"installed": False, "version": None, "configured": False, "missing": []}
    cli = shutil.which(a["cli"], path=env.get("PATH"))
    if cli:
        out["installed"] = True
        try:
            p = subprocess.run([cli, "--version"], capture_output=True, env=env, timeout=5,
                               encoding="utf-8", errors="replace")
            out["version"] = (p.stdout.strip().splitlines() or [None])[0] if p.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        with open(os.path.join(root, *a["config"].split("/")), encoding="utf-8") as f:
            hooks = json.load(f).get("hooks", {})
    except (OSError, ValueError):
        out["missing"] = [a["config"]]
        return out
    for event, script, arg in a["hooks"]:
        commands = [h.get("command", "") for g in hooks.get(event, []) for h in g.get("hooks", [])]
        if not any(_has(c, script, arg) for c in commands):
            out["missing"].append("%s: %s%s" % (event, script, " " + arg if arg else ""))
    out["configured"] = not out["missing"]
    return out


def doctor(root, env=None):
    return {rt: dict(health_check(rt, root, env),
                     capabilities={n: {"status": s, "how": how} for n, (s, how) in a["capabilities"].items()})
            for rt, a in ADAPTERS.items()}


def _markdown(report):
    lines = []
    for rt, h in report.items():
        state = "installed %s" % (h["version"] or "(version unknown)") if h["installed"] else "not installed"
        conf = "configured" if h["configured"] else "not configured: missing " + ", ".join(h["missing"])
        lines.append("%s: %s · %s" % (rt, state, conf))
    names = list(report)
    lines += ["", "| Capability | " + " | ".join(names) + " |", "|---" * (len(names) + 1) + "|"]
    for cap in CAPABILITIES:
        cells = ["%s: %s" % (report[rt]["capabilities"][cap]["status"], report[rt]["capabilities"][cap]["how"])
                 for rt in names]
        lines.append("| `%s` | %s |" % (cap, " | ".join(cells)))
    return "\n".join(lines)


def main(argv):
    if len(argv) < 2 or argv[1] != "doctor":
        print(__doc__.strip())
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # the report uses "·"; Windows pipes default to cp1252
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    report = doctor(root)
    print(json.dumps(report, indent=2) if "--json" in argv else _markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
