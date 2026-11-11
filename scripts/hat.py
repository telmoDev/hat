#!/usr/bin/env python3
"""hat's global home: the project registry and the lookup the hooks use (G1, docs/meta-harness/global-install.md).
  python3 scripts/hat.py resolve [<folder>]          the project <folder> belongs to: "<id>\t<root>", or exit 1
  python3 scripts/hat.py project add [<root>]        register a project (default: the git top level, or the folder)
  python3 scripts/hat.py project list                every project, with "missing" when its root is gone
  python3 scripts/hat.py project move <id> <root>    point a project at its new root
  python3 scripts/hat.py project remove <id>         unregister a project; its state stays in the home
  python3 scripts/hat.py migrate <workspace> [--dry-run]  move a per-project workspace's state and rules into hat
  python3 scripts/hat.py status                      every project: its layer, resume point, active tasks, last session
  python3 scripts/hat.py doctor                      is hat installed and healthy on this machine (exit 1 if not)
  python3 scripts/hat.py context [<folder>]          the session-start header of the project, as hook JSON
  python3 scripts/hat.py commit <message>            commit the current project's state in hat's home
  python3 scripts/hat.py resolve-payload < payload   resolve the "cwd" of a hook's JSON: "<id>\t<root>\t<state>"
The home is ~/.hat (HAT_HOME overrides it): projects.toml is the registry, projects/<id>/ each project's state.
The home is a local git repo (no remote unless the user adds one); telemetry, handoff and tmp stay out of it.
Nothing is ever written inside a project. `resolve` reads only and prints nothing outside a project, so a hook can
call it in every session. Standard library only, no network, no model calls.
"""
import hashlib
import json
import os
import re
import subprocess
import sys


def home():
    return os.environ.get("HAT_HOME") or os.path.join(os.path.expanduser("~"), ".hat")


def norm(path):
    """One spelling per folder: absolute, symlinks resolved, forward slashes."""
    return os.path.realpath(os.path.abspath(path)).replace("\\", "/").rstrip("/") or "/"


def key(path):
    """Comparable form of a norm()'d path: case-insensitive on Windows. (os.path.normcase would also turn its
    slashes back into backslashes.)"""
    return path.lower() if os.name == "nt" else path


def same(a, b):
    return key(a) == key(b)


def inside(path, root):
    """path is root or below it."""
    path, root = key(path), key(root)
    return path == root or path.startswith(root.rstrip("/") + "/")


def load():
    """{id: {"root": ..., ...}} from projects.toml (the subset hat writes: [project.<id>] and string keys).
    A table without a root is left out, so no lookup ever matches an empty root."""
    try:
        with open(os.path.join(home(), "projects.toml"), encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return {}
    projects, cur = {}, None
    for line in text.splitlines():
        m = re.match(r'\s*\[project\.([A-Za-z0-9_.-]+)\]\s*$', line)
        if m:
            cur = projects.setdefault(m.group(1), {})
            continue
        m = re.match(r'\s*([a-z_]+)\s*=\s*"((?:[^"\\]|\\.)*)"\s*$', line)
        if m and cur is not None:
            cur[m.group(1)] = m.group(2).replace('\\"', '"').replace("\\\\", "\\")
    return {pid: p for pid, p in projects.items() if p.get("root")}


def save(projects):
    lines = ["# hat's project registry: written by `hat project add|move`. One table per project."]
    for pid in sorted(projects):
        lines += ["", "[project.%s]" % pid]
        for k in sorted(projects[pid]):
            lines.append('%s = "%s"' % (k, projects[pid][k].replace("\\", "\\\\").replace('"', '\\"')))
    os.makedirs(home(), exist_ok=True)
    path = os.path.join(home(), "projects.toml")
    with open(path + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(path + ".tmp", path)


def resolve(folder):
    """(id, root) of the registered project folder is in, or None."""
    folder = norm(folder)
    hits = [(pid, p["root"]) for pid, p in load().items() if "root" in p and inside(folder, p["root"])]
    return max(hits, key=lambda h: len(h[1])) if hits else None


def default_root(cwd):
    p = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True, encoding="utf-8")
    return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else cwd


CLONE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IGNORE_LINES = ("projects/*/telemetry.db*", "projects/*/handoff/", "projects/*/tmp/", "*.tmp",
                "backup/", "install.json", "projects/*/migrated-layer/")  # backup/ may hold settings with tokens; install.json is this machine's


def state(pid):
    return os.path.join(home(), "projects", pid)


def git(*args):
    return subprocess.run(["git", "-C", home()] + list(args), capture_output=True, encoding="utf-8",
                          errors="replace")


def record(message, *paths):
    """Commit paths (relative to the home) with message; the home becomes a git repo on first use. Returns
    "committed", "nothing to commit" or the error, and never raises: a registration never depends on git."""
    try:
        if not os.path.isdir(os.path.join(home(), ".git")) and git("init", "-q").returncode != 0:
            return "git init failed"
        ignore = os.path.join(home(), ".gitignore")
        have = open(ignore, encoding="utf-8").read().splitlines() if os.path.isfile(ignore) else []
        missing = [l for l in IGNORE_LINES if l not in have]
        if missing:  # a new home, or one from an older hat
            with open(ignore, "a", encoding="utf-8", newline="\n") as f:
                f.write(("" if have else "# hat's home: what is regenerated or local to this machine stays out of git.\n")
                        + "\n".join(missing) + "\n")
            paths += (".gitignore",)
        tracked = set(git("ls-files", "--", *paths).stdout.split())
        present = [p for p in paths if os.path.exists(os.path.join(home(), p)) or p in tracked
                   or any(t.startswith(p.rstrip("/") + "/") for t in tracked)]
        if present:
            git("add", "-A", "--", *present)
        if git("diff", "--cached", "--quiet").returncode == 0:
            return "nothing to commit"
        who = [] if git("config", "user.email").stdout.strip() else ["-c", "user.name=hat", "-c", "user.email=hat@localhost"]
        p = subprocess.run(["git", "-C", home()] + who + ["commit", "-q", "-m", message], capture_output=True,
                           encoding="utf-8", errors="replace")
        return "committed" if p.returncode == 0 else "git commit failed: " + (p.stderr or p.stdout).strip()[:200]
    except OSError as err:
        return "git: %s" % err


def config(pid):
    out = {}
    try:
        with open(os.path.join(state(pid), "config"), encoding="utf-8") as f:
            for line in f:
                m = re.match(r'\s*([A-Z_]+)=["\']?(.*?)["\']?\s*$', line)
                if m:
                    out[m.group(1)] = m.group(2)
    except OSError:
        pass
    return out


def context(folder):
    """The session-start header: which project, where its state, guide and rules are. Short on purpose."""
    hit = resolve(folder)
    if not hit:
        return None
    pid, root = hit
    st, conf = norm(state(pid)), config(pid)
    lines = ["hat project %s · root %s · state %s" % (pid, root, st),
             "Guide: %s/guide/AGENTS.md: read it before anything else, then the project rules: %s/rules.md."
             % (norm(CLONE), st),
             "In the guide, <hat> is %s, <root> is %s and <state> is %s." % (norm(CLONE), root, st)]
    if conf.get("REPOS"):
        lines.append("Repos: %s%s" % (conf["REPOS"], " · bases: " + conf["BASE_BRANCHES"] if conf.get("BASE_BRANCHES") else ""))
    return "\n".join(lines)


STATUS = re.compile(r"^Status:\s*(\w+)(?:.*?·\s*Next:\s*(.*))?$", re.M)


def _resume(pid):
    """The first item under ## Resume in the project's NEXT_STEPS, or None."""
    try:
        with open(os.path.join(state(pid), "memory", "NEXT_STEPS.md"), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    m = re.search(r"^## Resume\s*\n((?:- .*\n?)+)", text, re.M)
    first = m.group(1).splitlines()[0][2:].strip() if m else ""
    return first if first and first.lower() != "none" else None


def _active_tasks(pid):
    folder, out = os.path.join(state(pid), "tasks"), []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not name.endswith(".md"):
            continue
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            m = STATUS.search(f.read())
        if m and m.group(1) == "active":
            out.append("%s: %s" % (name[:-3], (m.group(2) or "—").strip()))
    return out


def _last_session(pid):
    db = os.path.join(state(pid), "telemetry.db")
    if not os.path.isfile(db):
        return None
    import sqlite3
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True, timeout=1)
        try:
            row = con.execute("SELECT max(coalesce(finished_at, started_at)), count(*) FROM runs").fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    return "%s · %d sessions" % row if row and row[0] else None


def status():
    projects = load()
    if not projects:
        print("hat: no projects registered (python3 %s/scripts/hat.py project add, from a project's root)"
              % norm(CLONE))
        return 0
    for pid, p in sorted(projects.items()):
        root = p["root"]
        if not os.path.isdir(root):
            layer = "root missing (hat project move %s <root>, or remove)" % pid
        elif os.path.isdir(os.path.join(root, ".orchestrator")) and os.path.isfile(os.path.join(state(pid), "migrated.json")):
            layer = "migrated; its old layer still runs until: hat migrate %s --cleanup" % root
        elif os.path.isdir(os.path.join(root, ".orchestrator")):
            layer = "own layer: hat leaves it alone until it is migrated"
        else:
            layer = "hat"
        tasks = _active_tasks(pid)
        print("%s  %s" % (pid, root))
        print("  layer: " + layer)
        print("  resume: " + (_resume(pid) or "—"))
        print("  tasks: " + ("%d active · %s" % (len(tasks), "; ".join(tasks)) if tasks else "none active"))
        print("  last session: " + (_last_session(pid) or "—"))
    return 0


def doctor():
    problems, lines = 0, []
    def say(ok, text):
        nonlocal problems
        problems += 0 if ok else 1
        lines.append(("ok      " if ok else "problem ") + text)
    say(sys.version_info >= (3, 8), "python %d.%d" % sys.version_info[:2])
    import shutil
    claude = shutil.which("claude")
    version = None
    if claude:
        try:
            version = subprocess.run([claude, "--version"], capture_output=True, encoding="utf-8", timeout=5,
                                     errors="replace").stdout.strip().splitlines()[0]
        except (OSError, subprocess.SubprocessError, IndexError):
            pass
    say(bool(claude), "claude: " + (version or "installed") if claude else "claude: not found on PATH")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import hat_install
    lacking = hat_install.missing()
    say(not lacking, "global install" + (": missing %d (bash install.sh --global)" % len(lacking) if lacking else ""))
    if os.path.isdir(home()):
        dirty = git("status", "--porcelain").stdout.strip() if os.path.isdir(os.path.join(home(), ".git")) else None
        say(dirty is not None, "hat's home %s is a git repo" % norm(home()) if dirty is not None
            else "hat's home %s is not a git repo yet (it becomes one at the first project add)" % norm(home()))
        if dirty:
            lines.append("note    hat's home has uncommitted changes: %d paths" % len(dirty.splitlines()))
    for pid, p in sorted(load().items()):
        say(os.path.isdir(p["root"]), "project %s: %s" % (pid, p["root"] if os.path.isdir(p["root"])
                                                          else "root missing: " + p["root"]))
    print("\n".join(lines))
    print("hat doctor: " + ("ok" if not problems else "%d problem(s)" % problems))
    return 1 if problems else 0


def offer(folder):
    """One line for the session start where hat isn't running yet, or None: a workspace with the old layer
    (migrate it, or clean it up once migrated), an unregistered git repo (register it, decision G-D1)."""
    folder, hat_py = norm(folder), norm(os.path.join(CLONE, "scripts", "hat.py"))
    layer, d = None, folder
    while True:
        if os.path.isfile(os.path.join(d, ".orchestrator", "orchestrator.conf")):
            layer = d
            break
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    hit = resolve(folder)
    if layer and hit and hit[1] == layer:
        if os.path.isfile(os.path.join(state(hit[0]), "migrated.json")):
            return ("hat: this workspace is migrated to hat, but its old layer still runs. Offer the user, in one "
                    "line, to clean it up (one commit, git can undo it): python3 %s migrate %s --cleanup"
                    % (hat_py, layer))
        return "hat: this registered workspace still has its old layer. To move it: python3 %s migrate %s --dry-run" \
            % (hat_py, layer)
    if layer and not hit:
        return ("hat: this workspace has hat's old per-project layer. If the user wants it on the global install, "
                "keeping its own rules: python3 %s migrate %s --dry-run" % (hat_py, layer))
    if not hit:
        p = subprocess.run(["git", "-C", folder, "rev-parse", "--show-toplevel"], capture_output=True,
                           encoding="utf-8")
        if p.returncode == 0:
            return "hat isn't active in this repo. To use it here, from its root: python3 %s project add" % hat_py
    return None


def fail(msg):
    print("hat: " + msg, file=sys.stderr)
    return 1


def project_id(root):
    """<folder name>-<6 hex of the path>: two folders with the same name are two projects."""
    name = re.sub(r"[^A-Za-z0-9_-]+", "-", os.path.basename(root)).strip("-").lower() or "project"
    return "%s-%s" % (name, hashlib.sha256(root.encode("utf-8")).hexdigest()[:6])


def add(root):
    root = norm(root)
    if not os.path.isdir(root):
        return fail("no such folder: " + root)
    projects = load()
    for pid, p in projects.items():
        if same(p["root"], root):
            return fail("%s is already registered as %s" % (root, pid))
        if inside(root, p["root"]):
            return fail("%s is inside %s, registered as %s: one root per project" % (root, p["root"], pid))
        if inside(p["root"], root):
            return fail("%s contains %s, registered as %s: one root per project" % (root, p["root"], pid))
    pid = project_id(root)
    projects[pid] = {"root": root}
    save(projects)
    os.makedirs(state(pid), exist_ok=True)
    print("%s\t%s" % (pid, root))
    note = record("hat: add project " + pid, "projects.toml", "projects/" + pid)
    if note not in ("committed", "nothing to commit"):
        print("hat: registered, but not recorded in git: " + note, file=sys.stderr)
    return 0


def remove(pid):
    """Unregister a project. Its state (memory, tasks, telemetry) stays in the home, never deleted."""
    projects = load()
    if pid not in projects:
        return fail("no project " + pid)
    del projects[pid]
    save(projects)
    record("hat: remove project " + pid, "projects.toml")
    print("removed %s; its state stays in %s" % (pid, norm(state(pid))))
    return 0


def move(pid, root):
    root = norm(root)
    projects = load()
    if pid not in projects:
        return fail("no project " + pid)
    if not os.path.isdir(root):
        return fail("no such folder: " + root)
    for other, p in projects.items():
        if other != pid and (inside(root, p["root"]) or inside(p["root"], root)):
            return fail("%s overlaps %s, registered as %s" % (root, p["root"], other))
    projects[pid]["root"] = root
    save(projects)
    print("%s\t%s" % (pid, root))
    record("hat: move project %s to %s" % (pid, root), "projects.toml")
    return 0


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # status prints "—" and "·"; Windows pipes default to cp1252
    args = argv[1:]
    if args[:1] == ["resolve"] and len(args) <= 2:
        hit = resolve(args[1] if len(args) == 2 else os.getcwd())
        if hit:
            print("%s\t%s" % hit)
        return 0 if hit else 1
    if args[:1] == ["resolve-payload"] and len(args) == 1:
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except ValueError:
            return 1
        hit = resolve(payload.get("cwd") or os.getcwd()) if isinstance(payload, dict) else None
        if hit:
            print("%s\t%s\t%s" % (hit[0], hit[1], norm(state(hit[0]))))
        return 0 if hit else 1
    if args[:1] == ["migrate"]:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import hat_migrate
        return hat_migrate.main(args[1:])
    if args == ["status"]:
        return status()
    if args == ["doctor"]:
        return doctor()
    if args == ["offer-payload"]:
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except ValueError:
            return 0
        text = offer(payload.get("cwd") or os.getcwd()) if isinstance(payload, dict) else None
        if text:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
        return 0
    if args[:1] == ["context"] and len(args) <= 2:
        text = context(args[1] if len(args) == 2 else os.getcwd())
        if text:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
        return 0
    if args[:1] == ["commit"] and len(args) == 2:
        hit = resolve(os.getcwd())
        if not hit:
            return fail("not in a hat project: " + norm(os.getcwd()))
        note = record("%s: %s" % (hit[0], args[1]), "projects/" + hit[0])
        print(note)
        return 0 if note in ("committed", "nothing to commit") else 1
    if args[:2] == ["project", "add"] and len(args) <= 3:
        return add(args[2] if len(args) == 3 else default_root(os.getcwd()))
    if args[:2] == ["project", "list"] and len(args) == 2:
        for pid, p in sorted(load().items()):
            print("%s\t%s%s" % (pid, p["root"], "" if os.path.isdir(p["root"]) else "\tmissing"))
        return 0
    if args[:2] == ["project", "remove"] and len(args) == 3:
        return remove(args[2])
    if args[:2] == ["project", "move"] and len(args) == 4:
        return move(args[2], args[3])
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
