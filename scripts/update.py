#!/usr/bin/env python3
"""Update a workspace set up with this skill (v0.1.0 or later) to the skill's templates. Run it as
  bash update.sh [--dry-run] [--dev] <workspace-root>
Conservative and idempotent; it never deletes and never commits:
  - a file the workspace lacks is created; one identical to the template of its TEMPLATE_VERSION (read from the
    skill's v<version> tag) is updated; one the user changed is kept as is, and the new template is written next
    to it as <file>.new for a manual merge. An earlier <file>.new with other content stops the update.
  - .claude/settings.json gets the template's telemetry and session handoff hooks it lacks; nothing else in it
    changes.
  - orchestrator.conf gets the keys it lacks, appended with their comments; no value changes but
    TEMPLATE_VERSION, set last, so a partial run never claims the new version.
  - text the user adapts (AGENTS.md, CLAUDE.md, odd/README.md, memory/, task files) is never edited: the
    CHANGELOG's Workspaces steps since the workspace's version are printed for the agent or the user to apply.
Everything is checked and planned before the first write. A failure midway lists what was done and what is
pending. --dev updates from a skill that is not a release, leaving TEMPLATE_VERSION as it was: it is for testing
the skill, not for workspaces in regular use. At the next release, a file it wrote that changed again before the
release matches neither version and comes as <file>.new (one the snapshot didn't change updates as usual).
ORCH_UPDATE_FAIL_AT=<path> makes the step writing that path fail (tests only).
"""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(HERE, "templates")
LAYER = ["AGENTS.md", "CLAUDE.md", ".orchestrator", ".agents", ".claude", ".codex", "memory", "odd", ".gitignore",
         ".gitattributes"]


class Refuse(Exception):
    pass


def git(*args, cwd=HERE):
    # UTF-8 explicitly: the templates hold non-ASCII text, and Windows would decode with its locale code page.
    return subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, encoding="utf-8", errors="replace")


def read(path):
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()
    except FileNotFoundError:
        return None


def same(a, b):
    return a is not None and b is not None and a.replace("\r\n", "\n") == b.replace("\r\n", "\n")


def conf_values(text):
    return dict(re.findall(r'^\s*([A-Z_]+)=["\']?(.*?)["\']?\s*$', text, re.M))


def version_tuple(v):
    return tuple(int(x) for x in v.split("."))


def at_version(src, rel):
    """A template file as the v<src> release had it, or None if it had none."""
    r = git("show", "v%s:templates/%s" % (src, rel))
    return r.stdout if r.returncode == 0 else None


def add_telemetry_hooks(settings, template, scripts=("telemetry.sh",)):
    """Add to settings (a .claude/settings.json dict) the template's hooks that run one of scripts and it lacks;
    returns how many. The benchmark uses it with the default, telemetry only (its measurement layer)."""
    added = 0
    hooks = settings.setdefault("hooks", {})
    for event, groups in template.get("hooks", {}).items():
        for g in groups:
            for h in g["hooks"]:
                if not any(s in h.get("command", "") for s in scripts):
                    continue
                have = [x.get("command") for grp in hooks.get(event, []) for x in grp.get("hooks", [])]
                if h["command"] in have:
                    continue
                group = {"matcher": g["matcher"]} if "matcher" in g else {}
                group["hooks"] = [h]
                hooks.setdefault(event, []).append(group)
                added += 1
    return added


def plan(root, dev):
    """(ops, notes, versions) or Refuse. Reads only."""
    conf_path = os.path.join(root, ".orchestrator", "orchestrator.conf")
    conf = read(conf_path)
    if conf is None:
        if os.path.exists(os.path.join(root, ".claude", "orchestrator.conf")):
            raise Refuse("set up before v0.1.0: run scripts/migrate.sh first")
        raise Refuse("not an orchestrator workspace: no .orchestrator/orchestrator.conf")
    vals = conf_values(conf)
    src = vals.get("TEMPLATE_VERSION", "")
    if not re.fullmatch(r"\d+\.\d+\.\d+", src):
        raise Refuse("TEMPLATE_VERSION is missing or not x.y.z in .orchestrator/orchestrator.conf: set it to the "
                     "release the workspace was set up or last updated with")
    if git("rev-parse", "--git-dir").returncode != 0:
        raise Refuse("this skill is not a git clone, so the workspace's release can't be read")
    if git("rev-parse", "-q", "--verify", "refs/tags/v%s" % src).returncode != 0:
        raise Refuse("no tag v%s in this skill's clone (%s): fetch its tags (git fetch --tags) or fix "
                     "TEMPLATE_VERSION" % (src, HERE))
    target = (read(os.path.join(HERE, "VERSION")) or "").strip()
    tag = git("describe", "--exact-match", "--tags", "HEAD").stdout.strip()
    clean = git("status", "--porcelain", "--", "templates", "scripts", "VERSION").stdout.strip() == ""
    released = tag == "v%s" % target and clean
    if not released and not dev:
        raise Refuse("this skill is not a release (HEAD is not v%s with a clean tree): check out a release tag, or "
                     "pass --dev to update without claiming a version" % target)
    if released and version_tuple(src) > version_tuple(target):
        raise Refuse("the workspace (v%s) is newer than this skill (v%s): update the skill instead" % (src, target))
    if os.path.isdir(os.path.join(root, ".git")):
        dirty = git("status", "--porcelain", "--", *[p for p in LAYER if os.path.exists(os.path.join(root, p))],
                    cwd=root).stdout.strip()
        if dirty:
            raise Refuse("uncommitted changes in the orchestration layer: commit or stash them first\n" + dirty)

    root_shown = root.replace("\\", "/")
    ops, attention, conflicts = [], [], []

    def managed(rel, new, ref):
        cur = read(os.path.join(root, rel))
        if cur is None:
            ops.append({"rel": rel, "action": "create", "text": new})
        elif same(cur, new):
            return
        elif ref is not None and same(cur, ref):
            ops.append({"rel": rel, "action": "update", "text": new})
        else:
            copy = rel + ".new"
            old = read(os.path.join(root, copy))
            if old is None:
                ops.append({"rel": copy, "action": "new", "text": new, "of": rel})
            elif not same(old, new):
                conflicts.append(copy)
            attention.append(copy)

    for sub in ("scripts", "hooks"):
        for name in sorted(os.listdir(os.path.join(TPL, "orchestrator", sub))):
            p = os.path.join(TPL, "orchestrator", sub, name)
            if os.path.isfile(p):
                managed(".orchestrator/%s/%s" % (sub, name), read(p),
                        at_version(src, "orchestrator/%s/%s" % (sub, name)))
    if read(os.path.join(root, ".orchestrator", "rates.json")) is None:
        ops.append({"rel": ".orchestrator/rates.json", "action": "create",
                    "text": read(os.path.join(TPL, "orchestrator", "rates.json"))})
    skills_changed = False
    for name in sorted(os.listdir(os.path.join(TPL, "skills"))):
        new = read(os.path.join(TPL, "skills", name, "SKILL.md")).replace("{{ROOT}}", root_shown)
        ref = at_version(src, "skills/%s/SKILL.md" % name)
        n = len(ops)
        managed(".agents/skills/%s/SKILL.md" % name, new, ref and ref.replace("{{ROOT}}", root_shown))
        skills_changed = skills_changed or len(ops) > n
    if conflicts:
        raise Refuse("an earlier .new copy differs from this update's: merge or remove it, then run again: "
                     + ", ".join(conflicts))

    claude = os.path.isdir(os.path.join(root, ".claude"))
    if claude:
        rel = ".claude/settings.json"
        tpl = json.loads(read(os.path.join(TPL, "claude", "settings.json")))
        cur_text = read(os.path.join(root, rel))
        if cur_text is None:
            ops.append({"rel": rel, "action": "create", "text": json.dumps(tpl, indent=2) + "\n"})
        else:
            try:
                cur = json.loads(cur_text)
            except ValueError:
                raise Refuse(rel + " is not valid JSON: fix it first")
            added = add_telemetry_hooks(cur, tpl, ("telemetry.sh", "session-handoff.sh"))
            if added:
                ops.append({"rel": rel, "action": "merge", "text": json.dumps(cur, indent=2) + "\n",
                            "note": "added %d telemetry and session handoff hooks" % added})

    gi = read(os.path.join(root, ".gitignore"))
    if gi is not None:
        have = set(gi.splitlines())
        missing = [l for l in read(os.path.join(TPL, "gitignore")).splitlines()
                   if l and not l.startswith("#") and l not in have]
        if missing:
            ops.append({"rel": ".gitignore", "action": "merge", "note": "added " + ", ".join(missing),
                        "text": gi + ("" if gi.endswith("\n") else "\n") + "\n".join(missing) + "\n"})
    elif vals.get("ROOT_GIT") == "no" and os.path.isfile(os.path.join(root, ".git", "info", "exclude")):
        ex = read(os.path.join(root, ".git", "info", "exclude"))
        if "/.orchestrator/telemetry/" not in ex.splitlines():
            ops.append({"rel": ".git/info/exclude", "action": "merge", "note": "added /.orchestrator/telemetry/",
                        "text": ex + ("" if ex.endswith("\n") else "\n") + "/.orchestrator/telemetry/\n"})

    if claude and skills_changed:
        ops.append({"rel": ".claude/skills/", "action": "run", "note": "sync-skills.sh"})

    # orchestrator.conf last: the keys it lacks, then the version.
    appended, block = [], []
    for line in read(os.path.join(TPL, "orchestrator", "orchestrator.conf")).splitlines():
        m = re.match(r"([A-Z_]+)=", line)
        if line.startswith("#"):
            block.append(line)
            continue
        if m and m.group(1) not in vals and "{{" not in line:
            appended += block + [line]
        block = []
    new_conf = conf
    if appended:
        new_conf += ("" if new_conf.endswith("\n") else "\n") + "\n".join(appended) + "\n"
    if released and target != src:
        new_conf = re.sub(r'^TEMPLATE_VERSION=.*$', 'TEMPLATE_VERSION="%s"' % target, new_conf, flags=re.M)
    if new_conf != conf:
        keys = [re.match(r"([A-Z_]+)=", l).group(1) for l in appended if re.match(r"[A-Z_]+=", l)]
        note = ", ".join(["added " + k for k in keys] + (["TEMPLATE_VERSION %s -> %s" % (src, target)]
                                                         if released and target != src else []))
        ops.append({"rel": ".orchestrator/orchestrator.conf", "action": "merge", "text": new_conf, "note": note})

    return ops, attention, {"src": src, "target": target, "released": released}


def changelog_steps(src, target, released):
    """The CHANGELOG sections after src (up to target, or Unreleased too for a dev skill), with their Workspaces."""
    text = read(os.path.join(HERE, "CHANGELOG.md")) or ""
    out = []
    for head, body in re.findall(r"^## (.+?)\n(.*?)(?=^## |\Z)", text, re.S | re.M):
        m = re.match(r"v(\d+\.\d+\.\d+)", head)
        if m:
            v = version_tuple(m.group(1))
            if v <= version_tuple(src) or (released and v > version_tuple(target)):
                continue
        elif head.strip() != "Unreleased" or (released and ("## v%s" % target) in text):
            continue
        steps = re.findall(r"\*\*Workspaces:?\*\*:?(.*?)(?=\n\n|\Z)", body, re.S)  # "**Workspaces:**" in releases
        if steps:
            out.append("### %s\n%s" % (head.strip(), "\n".join("-" + s.rstrip() for s in steps)))
    return out


def execute(root, ops):
    """Run the ops in order. (True, done) or (False, done, failed op, error)."""
    fail_at = os.environ.get("ORCH_UPDATE_FAIL_AT")
    done = []
    for op in ops:
        try:
            if fail_at and op["rel"] == fail_at:
                raise OSError("simulated failure (ORCH_UPDATE_FAIL_AT)")
            if op["action"] == "run":
                # The bash on PATH: on Windows a bare "bash" can resolve to WSL's in System32 before Git Bash.
                r = subprocess.run([shutil.which("bash") or "bash", ".orchestrator/scripts/sync-skills.sh"], cwd=root,
                                   capture_output=True, encoding="utf-8", errors="replace")
                if r.returncode != 0:
                    raise OSError("sync-skills.sh failed: " + (r.stderr or r.stdout).strip()[:200])
            else:
                path = os.path.join(root, *op["rel"].split("/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                mode = os.stat(path).st_mode if os.path.exists(path) else None
                tmp = path + ".update-tmp"
                with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                    f.write(op["text"])
                if mode is not None:
                    os.chmod(tmp, mode)
                elif path.endswith((".sh", ".py")):
                    os.chmod(tmp, 0o755)
                os.replace(tmp, path)  # atomic per file: a file is either the old or the new one
        except Exception as err:
            if op["action"] != "run" and os.path.exists(os.path.join(root, *op["rel"].split("/")) + ".update-tmp"):
                os.remove(os.path.join(root, *op["rel"].split("/")) + ".update-tmp")
            return False, done, op, err
        done.append(op)
    return True, done, None, None


def describe(op):
    if op["action"] == "new":
        return "new    %s (you changed %s: merge it by hand)" % (op["rel"], op["of"])
    if op["action"] == "run":
        return "run    %s (copies the skills into %s)" % (op["note"], op["rel"])
    return "%-6s %s%s" % (op["action"], op["rel"], " (%s)" % op["note"] if op.get("note") else "")


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # the CHANGELOG steps aren't ASCII; Windows pipes default to cp1252
    args = argv[1:]
    dry, dev = "--dry-run" in args, "--dev" in args
    rest = [a for a in args if a not in ("--dry-run", "--dev")]
    if len(rest) != 1:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    root = os.path.abspath(rest[0])
    try:
        ops, attention, v = plan(root, dev)
    except Refuse as err:
        print("update: refused: %s\nNothing was changed." % err)
        return 1
    print("orchestrator update: workspace v%s -> skill v%s%s" % (
        v["src"], v["target"], "" if v["released"] else " (not a release: --dev)"))
    for op in ops:
        print(describe(op))
    steps = changelog_steps(v["src"], v["target"], v["released"])
    pending_new = sorted(set(attention) | {op["rel"] for op in ops if op["action"] == "new"})
    if dry:
        print("(dry run: nothing written)" if ops else "No changes: the workspace already matches this skill.")
        return 0
    ok, done, failed, err = execute(root, ops)
    if not ok:
        print("\nUpdate incomplete: %s failed: %s" % (failed["rel"], err))
        print("Done:\n" + ("\n".join("  - " + describe(o) for o in done) or "  - nothing"))
        print("Pending:\n" + "\n".join("  - " + describe(o) for o in ops[len(done):]))
        print("TEMPLATE_VERSION was not changed. Fix the cause and run update.sh again: what's done is kept.")
        return 1
    print("No changes: the workspace already matches this skill." if not ops else
          "\nUpdated to v%s." % v["target"] if v["released"] else
          "\nUpdated. TEMPLATE_VERSION left at %s: this skill is not a release. --dev is for testing the skill, "
          "not for workspaces in regular use: at the next release, a file this run wrote that changed again "
          "comes as <file>.new." % v["src"])
    if pending_new or steps:
        print("\nNeeds your attention:")
        for p in pending_new:
            print("  - %s: the new template next to your changed file; merge it into %s, then delete it"
                  % (p, p[:-4]))
        if steps:
            print("  - the text files the update never edits: apply these Workspaces steps by hand")
            print("\n" + "\n\n".join(steps))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
