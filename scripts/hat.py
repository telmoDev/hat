#!/usr/bin/env python3
"""hat's global home: the project registry and the lookup the hooks use (G1, docs/meta-harness/global-install.md).
  python3 scripts/hat.py resolve [<folder>]          the project <folder> belongs to: "<id>\t<root>", or exit 1
  python3 scripts/hat.py project add [<root>]        register a project (default: the git top level, or the folder)
  python3 scripts/hat.py project list                every project, with "missing" when its root is gone
  python3 scripts/hat.py project move <id> <root>    point a project at its new root
The home is ~/.hat (HAT_HOME overrides it): projects.toml is the registry, projects/<id>/ each project's state.
Nothing is ever written inside a project. `resolve` reads only and prints nothing outside a project, so a hook can
call it in every session. Standard library only, no network, no model calls.
"""
import hashlib
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


def fail(msg):
    print("hat: " + msg, file=sys.stderr)
    return 1


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
    name = re.sub(r"[^A-Za-z0-9_-]+", "-", os.path.basename(root)).strip("-").lower() or "project"
    pid = "%s-%s" % (name, hashlib.sha256(root.encode("utf-8")).hexdigest()[:6])
    projects[pid] = {"root": root}
    save(projects)
    os.makedirs(os.path.join(home(), "projects", pid), exist_ok=True)
    print("%s\t%s" % (pid, root))
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
    return 0


def main(argv):
    args = argv[1:]
    if args[:1] == ["resolve"] and len(args) <= 2:
        hit = resolve(args[1] if len(args) == 2 else os.getcwd())
        if hit:
            print("%s\t%s" % hit)
        return 0 if hit else 1
    if args[:2] == ["project", "add"] and len(args) <= 3:
        return add(args[2] if len(args) == 3 else default_root(os.getcwd()))
    if args[:2] == ["project", "list"] and len(args) == 2:
        for pid, p in sorted(load().items()):
            print("%s\t%s%s" % (pid, p["root"], "" if os.path.isdir(p["root"]) else "\tmissing"))
        return 0
    if args[:2] == ["project", "move"] and len(args) == 4:
        return move(args[2], args[3])
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
