#!/usr/bin/env python3
"""hat's global install (G3, docs/meta-harness/global-install.md): wire hat once, for every project.
  python3 scripts/hat_install.py install     (bash install.sh --global)
  python3 scripts/hat_install.py uninstall   (bash install.sh --global --uninstall)
  python3 scripts/hat_install.py check       (bash install.sh --global --check)
install adds to ~/.claude/settings.json the hooks that call scripts/hat-hook.sh (they act only in registered
projects), a short pointer block to ~/.claude/CLAUDE.md (and ~/.codex/AGENTS.md when Codex is set up), the agents
guide/agents/hat-*.md to ~/.claude/agents/, and links from ~/.claude/skills/ and ~/.agents/skills/ to guide/skills/.
Everything it adds is recorded in ~/.hat/install.json, and uninstall removes exactly that. It keeps every other
setting, backs settings.json up before its first change, and refuses, changing nothing, when a file it would write
already exists and isn't its own. Compaction settings are only proposed: they stay the user's. Standard library
only, no network, no model calls.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys

CLONE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(CLONE, "scripts", "hat-hook.sh").replace("\\", "/")
WINDOWS = os.name == "nt"
BEGIN, END = "<!-- hat:begin -->", "<!-- hat:end -->"
POINTER = """%s
hat is installed (%s). In a project registered with hat, the session start names the project and tells you
to read hat's guide and the project's rules: follow them. Elsewhere hat adds nothing; ignore this note. To use
hat in a project: `python3 %s/scripts/hat.py project add` from its root.
%s
""" % (BEGIN, CLONE.replace("\\", "/"), CLONE.replace("\\", "/"), END)

# (event, matcher, hook, args, timeout): what the per-project settings template wires, through the global entry.
HOOKS = [
    ("SessionStart", None, "context", "", 10),
    ("SessionStart", None, "session-memory", "", 10),
    ("SessionStart", None, "decision-index", "", 10),
    ("SessionStart", None, "session-handoff", "start", 10),
    ("SessionStart", None, "telemetry", "hook claude", 10),
    ("SessionEnd", None, "telemetry", "hook claude", 5),
    ("SessionEnd", None, "session-handoff", "end", 5),
    ("SubagentStart", None, "telemetry", "hook claude", 5),
    ("SubagentStop", None, "telemetry", "hook claude", 5),
    ("PostToolUse", "Agent|Task", "telemetry", "hook claude", 5),
    ("PostToolUseFailure", "Agent|Task", "telemetry", "hook claude", 5),
]


def home(*parts):
    return os.path.join(os.path.expanduser("~"), *parts)


def hat_home(*parts):
    return os.path.join(os.environ.get("HAT_HOME") or home(".hat"), *parts)


def command(hook, args):
    return ('bash "%s" %s %s' % (HOOK, hook, args)).strip()


def read(path):
    try:
        with open(path, encoding="utf-8", newline="") as f:  # bytes as they are: CRLF stays CRLF
            return f.read()
    except FileNotFoundError:
        return None


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".hat-tmp", "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(path + ".hat-tmp", path)


def is_link(path):
    try:
        os.readlink(path)  # a symlink, or a junction on Windows
        return True
    except (OSError, ValueError, AttributeError):
        return False


def link(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if WINDOWS:  # a directory junction needs no admin rights or developer mode
        subprocess.run(["cmd", "/c", "mklink", "/J", dst, src], check=True, capture_output=True)
    else:
        os.symlink(src, dst)


def unlink(path):
    if WINDOWS and os.path.isdir(path) and not os.path.islink(path):
        os.rmdir(path)  # removes the junction, never its target
    else:
        os.remove(path)


# Only the skills the orchestrator invokes are linked globally: every session on the machine lists their
# descriptions, in a project or not. The standards and pre-pr-review are read by path from the brief.
GLOBAL_SKILLS = ("orchestrator-metrics", "sync-memory")


def skills():
    base = os.path.join(CLONE, "guide", "skills")
    return [n for n in GLOBAL_SKILLS if os.path.isfile(os.path.join(base, n, "SKILL.md"))]


def agents():
    base = os.path.join(CLONE, "guide", "agents")
    return sorted(n for n in os.listdir(base) if n.endswith(".md"))


def manifest():
    text = read(hat_home("install.json"))
    return json.loads(text) if text else {"agents": [], "links": [], "blocks": [], "hooks": []}


def targets():
    """Every file or link install would own: (kind, path, source)."""
    out = [("agent", home(".claude", "agents", n), os.path.join(CLONE, "guide", "agents", n)) for n in agents()]
    for name in skills():
        src = os.path.join(CLONE, "guide", "skills", name)
        out += [("link", home(".claude", "skills", name), src), ("link", home(".agents", "skills", name), src)]
    return out


def conflicts(m):
    bad = []
    for kind, path, src in targets():
        if not os.path.lexists(path) or path in m["agents"] + m["links"]:
            continue
        if kind == "agent" and read(path) == read(src):
            continue
        if kind == "link" and is_link(path) and os.path.realpath(path) == os.path.realpath(src):
            continue
        bad.append(path)
    return bad


def add_block(path):
    text = read(path) or ""
    if BEGIN in text:
        return False
    write(path, text + ("" if not text or text.endswith("\n") else "\n") + ("\n" if text else "") + POINTER)
    return True


def remove_block(path):
    text = read(path)
    if text is None or BEGIN not in text:
        return
    start, end = text.index(BEGIN), text.index(END) + len(END)
    before, after = text[:start], text[end:].lstrip("\n")
    if before.endswith("\n\n") and not after:
        before = before[:-1]
    write(path, before + after)


def install():
    m = manifest()
    bad = conflicts(m)
    if bad:
        print("hat install: refused, nothing changed: these exist and aren't hat's; move them away first:\n  "
              + "\n  ".join(bad))
        return 1
    settings_path = home(".claude", "settings.json")
    text = read(settings_path)
    settings = json.loads(text) if text and text.strip() else {}
    hooks = settings.setdefault("hooks", {})
    added = []
    for event, matcher, hook, args, timeout in HOOKS:
        cmd = command(hook, args)
        if any(h.get("command") == cmd for g in hooks.get(event, []) for h in g.get("hooks", [])):
            continue
        group = {"matcher": matcher} if matcher else {}
        group["hooks"] = [{"type": "command", "command": cmd, "timeout": timeout, "shell": "bash"}]
        hooks.setdefault(event, []).append(group)
        added.append([event, cmd])
    if added:
        if text is not None and not m.get("backup"):
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            m["backup"] = hat_home("backup", "settings.json." + stamp)
            os.makedirs(os.path.dirname(m["backup"]), exist_ok=True)
            shutil.copy2(settings_path, m["backup"])
        write(settings_path, json.dumps(settings, indent=2) + "\n")
        m["hooks"] += added
    for path in [home(".claude", "CLAUDE.md")] + ([home(".codex", "AGENTS.md")] if os.path.isdir(home(".codex")) else []):
        if add_block(path) and path not in m["blocks"]:
            m["blocks"].append(path)
    wanted = {path for _, path, _ in targets()}
    for path in [p for p in m["links"] if p not in wanted]:  # linked by an older install
        if is_link(path):
            unlink(path)
        m["links"].remove(path)
    for kind, path, src in targets():
        if kind == "agent":
            if read(path) != read(src):
                write(path, read(src))
            if path not in m["agents"]:
                m["agents"].append(path)
        else:
            if not os.path.lexists(path):
                link(src, path)
            if path not in m["links"]:
                m["links"].append(path)
    write(hat_home("install.json"), json.dumps(m, indent=2) + "\n")
    print("hat installed for every project (%d hooks added, %d agents, %d skills linked)."
          % (len(added), len(agents()), len(skills())))
    if "autoCompactWindow" not in settings:
        print("Proposed, not set: \"autoCompactWindow\": 150000 in ~/.claude/settings.json, and the env "
              "CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS=100000, to compact before the context grows costly.")
    print("Register a project: python3 %s/scripts/hat.py project add  (from its root)" % CLONE.replace("\\", "/"))
    return 0


def uninstall():
    m = manifest()
    settings_path = home(".claude", "settings.json")
    text = read(settings_path)
    if text and m["hooks"]:
        settings = json.loads(text)
        ours = {cmd for _, cmd in m["hooks"]}
        hooks = settings.get("hooks", {})
        for event in list(hooks):
            groups = []
            for g in hooks[event]:
                g["hooks"] = [h for h in g.get("hooks", []) if h.get("command") not in ours]
                if g["hooks"]:
                    groups.append(g)
            if groups:
                hooks[event] = groups
            else:
                del hooks[event]
        if not hooks:
            settings.pop("hooks", None)
        write(settings_path, json.dumps(settings, indent=2) + "\n")
    for path in m["blocks"]:
        remove_block(path)
    for path in m["agents"]:
        if os.path.isfile(path):
            os.remove(path)
    for path in m["links"]:
        if is_link(path):
            unlink(path)
    if os.path.exists(hat_home("install.json")):
        os.remove(hat_home("install.json"))
    print("hat uninstalled: its hooks, pointer, agents and skill links are gone; projects' state stays in %s."
          % hat_home())
    return 0


def missing():
    """What the global install lacks on this machine (empty when it is complete)."""
    out, cmds = [], set()
    text = read(home(".claude", "settings.json"))
    if text:
        cmds = {h.get("command") for gs in json.loads(text).get("hooks", {}).values() for g in gs
                for h in g.get("hooks", [])}
    out += ["hook %s %s" % (e, command(h, a)) for e, _, h, a, _ in HOOKS if command(h, a) not in cmds]
    if BEGIN not in (read(home(".claude", "CLAUDE.md")) or ""):
        out.append("pointer in ~/.claude/CLAUDE.md")
    out += [path for _, path, _ in targets() if not os.path.exists(path)]
    return out


def check():
    missing_ = missing()
    for line in missing_:
        print("missing " + line)
    print("hat global install: " + ("ok" if not missing_ else "incomplete (bash install.sh --global)"))
    return 1 if missing_ else 0


def main(argv):
    if argv[1:] == ["install"]:
        return install()
    if argv[1:] == ["uninstall"]:
        return uninstall()
    if argv[1:] == ["check"]:
        return check()
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
