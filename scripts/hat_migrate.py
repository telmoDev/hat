#!/usr/bin/env python3
"""hat migrate (G6a, docs/meta-harness/global-install.md §8): move a workspace with the per-project layer to the
global install, saving everything that is the project's own first.
  python3 scripts/hat.py migrate <workspace> [--dry-run]
  python3 scripts/hat.py migrate <workspace> --refresh    after a migration, if the workspace kept working: bring
                                                        its new state over, keeping the review of rules.md and config
  python3 scripts/hat.py migrate <workspace> --cleanup    after a migration: remove hat's old layer, one commit
Each layer file is compared with the template of the workspace's TEMPLATE_VERSION (read from this clone's tag),
placeholders filled at setup counting as wildcards. What equals the template is hat's. What differs is the
project's: the adapted paragraphs of AGENTS.md (and its project sections, always) go verbatim to rules.md, other
changed or added layer files to overrides/, its checklist to checklist.md. memory/, odd/tasks/, the conf, the
telemetry store and the handoff state are copied as they are, and the whole layer to migrated-layer/ (git-ignored:
it may hold local settings). A check confirms every project-specific paragraph is saved before anything is
registered; one missing stops the migration. The workspace itself is never changed: its own layer keeps running
until it is cleaned up (G6b), and the global hooks leave it alone meanwhile. Standard library only.
"""
import datetime
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hat  # noqa: E402

CLONE = os.path.dirname(HERE)
LAYER = ["AGENTS.md", "CLAUDE.md", ".orchestrator", ".agents", ".claude", ".codex", "memory", "odd"]
PROJECT_SECTIONS = ("Layout", "Commands", "Repo guides", "How the repos connect", "Workspace rules")
COPIED = (".orchestrator/orchestrator.conf", ".orchestrator/pre-pr-checklist.md")  # saved as config / checklist.md
SKIP = (".orchestrator/telemetry/", ".orchestrator/tmp/", "memory/", "odd/tasks/")  # copied as state, not overrides


def fail(msg):
    print("hat migrate: " + msg, file=sys.stderr)
    return 1


def versions_since(version):
    """The workspace's release, every later one, and this clone's current templates ("HEAD"): a file equal to any
    of them is hat's (an update, or update --dev, may have brought a later one)."""
    tags = subprocess.run(["git", "-C", CLONE, "tag", "--list", "v*"], capture_output=True, encoding="utf-8").stdout
    key = lambda v: tuple(int(x) for x in v.split("."))
    later = sorted((t[1:] for t in tags.split() if re.fullmatch(r"v\d+\.\d+\.\d+", t)), key=key)
    return [v for v in later if key(v) >= key(version)] + ["HEAD"]


def at_version(version, rel):
    if version == "HEAD":
        path = os.path.join(CLONE, "templates", *rel.split("/"))
        return read(path) if os.path.isfile(path) else None
    p = subprocess.run(["git", "-C", CLONE, "show", "v%s:templates/%s" % (version, rel)], capture_output=True,
                       encoding="utf-8", errors="replace")
    return p.stdout if p.returncode == 0 else None


def pattern(template):
    """A template text as a regex: placeholders filled at setup ({{X}}) match anything."""
    parts = re.split(r"\{\{[A-Z_]+\}\}", template.strip())
    return re.compile(r"(?s)" + r".*?".join(re.escape(p) for p in parts) + r"\Z")


def paragraphs(text):
    return [p for p in re.split(r"\n\s*\n", text.replace("\r\n", "\n")) if p.strip()]


def sections(text):
    """[(heading or None, body)] split at ## and ### headings."""
    out = []
    for part in re.split(r"(?m)^(?=#{2,3} )", text.replace("\r\n", "\n")):
        m = re.match(r"#{2,3} (.+)\n", part)
        out.append((m.group(1).strip() if m else None, part))
    return out


def counterpart(rel):
    """The template a layer file was made from, or None for a file the user added."""
    parts = rel.split("/")
    if rel == "CLAUDE.md" or rel == "AGENTS.md":
        return rel
    if parts[0] == ".orchestrator" and len(parts) == 3 and parts[1] in ("scripts", "hooks"):
        return "orchestrator/%s/%s" % (parts[1], parts[2])
    if parts[0] in (".agents", ".claude") and len(parts) == 4 and parts[1] == "skills" and parts[3] == "SKILL.md":
        return "skills/%s/SKILL.md" % parts[2]
    if rel == ".claude/settings.json":
        return "claude/settings.json"
    if parts[0] == ".claude" and parts[1:2] == ["workflows"]:
        return "claude/workflows/" + "/".join(parts[2:])
    if parts[0] == ".claude" and parts[1:2] == ["agents"] and len(parts) == 3:
        return "agents/%s" % ("developer.md" if parts[2].endswith("-dev.md") else parts[2])
    if parts[0] == ".codex" and len(parts) == 2:
        return "codex/" + parts[1]
    if rel == ".orchestrator/rates.json":
        return "orchestrator/rates.json"
    if rel == "odd/README.md":
        return "odd/README.md"
    return None


def generated(ws, rel):
    """Files hat's scripts derive from others, or runtime leftovers: never the project's own text."""
    parts = rel.split("/")
    if "__pycache__" in parts or rel.endswith((".pyc", ".lock")) or rel == ".orchestrator/update-keep":
        return True
    if parts[:2] == [".claude", "skills"]:  # sync-skills.sh copies .agents/skills here
        twin = os.path.join(ws, ".agents", "skills", *parts[2:])
        return os.path.isfile(twin) and read(twin) == read(os.path.join(ws, *parts))
    if parts[:2] == [".codex", "agents"] and rel.endswith(".toml"):  # agent-to-codex.py, from .claude/agents
        return os.path.isfile(os.path.join(ws, ".claude", "agents", parts[2][:-5] + ".md"))
    return False


def layer_files(ws):
    for top in LAYER:
        p = os.path.join(ws, top)
        if os.path.isfile(p):
            yield top
        for d, dirs, files in os.walk(p) if os.path.isdir(p) else []:
            for name in sorted(files):
                yield os.path.relpath(os.path.join(d, name), ws).replace("\\", "/")


def read(path):
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        return f.read()


def plan(ws, version):
    """(rules text, {override rel: text}, checklist text or None, project paragraphs that must be saved)."""
    guide = read(os.path.join(ws, "AGENTS.md")) if os.path.isfile(os.path.join(ws, "AGENTS.md")) else ""
    template = at_version(version, "AGENTS.md") or ""
    known = [pattern(p) for p in paragraphs(template)]
    rules = ["# Project rules", "",
             "Saved verbatim by `hat migrate` from the workspace's AGENTS.md (template v%s): its project sections, "
             "and every paragraph that differs from the template. Review it with the user: what fits a config key "
             "moves to `config`, the rest stays here as the project's rules." % version]
    adapted, must = [], []
    for heading, body in sections(guide):
        if heading is None:
            continue
        if heading in PROJECT_SECTIONS:
            rules += ["", body.rstrip("\n")]
            must += paragraphs(body)
            continue
        own = [p for p in paragraphs(body)[1:] if not any(k.match(p.strip()) for k in known)]
        if own:
            adapted += ["", "### From › %s" % heading, ""] + ["\n\n".join(own)]
            must += own
    if adapted:
        rules += ["", "## Adapted from hat's guide"] + adapted
    overrides, checklist, since = {}, None, versions_since(version)
    for rel in layer_files(ws):
        if rel == "AGENTS.md" or rel in COPIED[:1] or rel.startswith(SKIP) or rel.endswith(".new") \
                or generated(ws, rel):
            continue
        text = read(os.path.join(ws, *rel.split("/")))
        tpl = counterpart(rel) if rel != COPIED[1] else "orchestrator/pre-pr-checklist.md"
        body = text.replace("\r\n", "\n").strip()
        refs = [at_version(v, tpl) for v in since] if tpl else []
        if any(r is not None and pattern(r).match(body) for r in refs):
            continue
        if rel == COPIED[1]:
            checklist = text
        else:
            overrides[rel] = text
    return "\n".join(rules) + "\n", overrides, checklist, must


def move_wrapper(ws, config, stage, st):
    """A GIT_WRAPPER inside the old layer would go with the cleanup: copy it to <state>/bin/ and point the config
    at it (an absolute path, which the scripts use as it is)."""
    text = read(config)
    m = re.search(r'^GIT_WRAPPER="?([^"\n]+)"?\s*$', text, re.M)
    if not m or os.path.isabs(m.group(1)) or not m.group(1).startswith(".orchestrator/"):
        return
    src = os.path.join(ws, *m.group(1).split("/"))
    if not os.path.isfile(src):
        return
    os.makedirs(os.path.join(stage, "bin"), exist_ok=True)
    shutil.copy2(src, os.path.join(stage, "bin", os.path.basename(src)))
    final = hat.norm(os.path.join(st, "bin", os.path.basename(src)))
    with open(config, "w", encoding="utf-8", newline="") as f:
        f.write(text[:m.start()] + 'GIT_WRAPPER="%s"' % final + text[m.end():])


def copy_state(ws, dst):
    """memory/, odd/tasks/, the telemetry store (a SQLite backup) and the handoff state of the workspace, into dst."""
    for sub, src in (("memory", os.path.join(ws, "memory")), ("tasks", os.path.join(ws, "odd", "tasks"))):
        shutil.rmtree(os.path.join(dst, sub), ignore_errors=True)
        os.makedirs(os.path.join(dst, sub))
        for n in sorted(os.listdir(src)) if os.path.isdir(src) else []:
            if n.endswith(".md"):
                shutil.copy2(os.path.join(src, n), os.path.join(dst, sub, n))
    db = os.path.join(ws, ".orchestrator", "telemetry", "telemetry.db")
    if os.path.isfile(db):
        src_db = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
        dst_db = sqlite3.connect(os.path.join(dst, "telemetry.db"))
        src_db.backup(dst_db)
        src_db.close()
        dst_db.close()
    handoff = os.path.join(ws, ".orchestrator", "tmp", "handoff")
    if os.path.isdir(handoff):
        shutil.rmtree(os.path.join(dst, "handoff"), ignore_errors=True)
        shutil.copytree(handoff, os.path.join(dst, "handoff"))


def copy_layer(ws, dst):
    shutil.rmtree(dst, ignore_errors=True)
    for top in LAYER:
        p = os.path.join(ws, top)
        target = os.path.join(dst, top)
        if os.path.isfile(p):
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(p, target)
        elif os.path.isdir(p):
            # symlinks=True: a link (e.g. .claude/agents into an app repo) is kept as a link, never its target
            shutil.copytree(p, target, symlinks=True, ignore=shutil.ignore_patterns("telemetry.db*"))


def refresh(ws):
    """Bring a migrated workspace's new state into hat's copy before its cleanup. The state's rules.md and config
    are the user's review: kept; a project paragraph new since the migration is appended to rules.md, and a conf
    key that now differs from the state's config is reported, not copied."""
    ws = hat.norm(ws)
    hit = hat.resolve(ws)
    info = os.path.join(hat.state(hit[0]), "migrated.json") if hit and hit[1] == ws else None
    if not info or not os.path.isfile(info):
        return fail("%s is not migrated: run hat migrate %s first" % (ws, ws))
    if os.path.isdir(os.path.join(ws, ".git")):
        dirty = subprocess.run(["git", "-C", ws, "status", "--porcelain", "--"]
                               + [p for p in LAYER if os.path.exists(os.path.join(ws, p))],
                               capture_output=True, encoding="utf-8").stdout.strip()
        if dirty:
            return fail("uncommitted changes in the orchestration layer: commit them first\n" + dirty)
    st = hat.state(hit[0])
    with open(info, encoding="utf-8") as f:
        data = json.load(f)
    rules_path = os.path.join(st, "rules.md")
    rules, overrides, _, must = plan(ws, data["template_version"])
    kept = read(rules_path) if os.path.isfile(rules_path) else ""
    new = [p.strip() for p in must if p.strip() not in kept]
    if new:
        kept = kept.rstrip("\n") + ("\n\n## Added since the migration\n" if "## Added since the migration" not in kept
                                    else "\n") + "\n" + "\n\n".join(new) + "\n"
        with open(rules_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(kept)
    copy_state(ws, st)
    shutil.rmtree(os.path.join(st, "overrides"), ignore_errors=True)
    for rel, text in overrides.items():
        p = os.path.join(st, "overrides", *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    copy_layer(ws, os.path.join(st, "migrated-layer"))
    ws_conf = dict(re.findall(r'^([A-Z_]+)="?([^"\n]*)"?\s*$', read(os.path.join(ws, ".orchestrator", "orchestrator.conf")), re.M))
    st_conf = dict(re.findall(r'^([A-Z_]+)="?([^"\n]*)"?\s*$', read(os.path.join(st, "config")), re.M))
    differ = sorted(k for k, v in ws_conf.items() if k not in ("GIT_WRAPPER",) and st_conf.get(k) != v)
    data["refreshed_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(info, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    note = hat.record("%s: refreshed from %s" % (hit[0], ws), "projects/" + hit[0])
    print("hat migrate --refresh: memory, tasks, telemetry, handoff and the layer copy brought over from %s; "
          "rules.md and config kept (%d new project paragraph(s) appended to rules.md); %s." % (ws, len(new), note))
    if differ:
        print("Conf keys that differ from the state's config (kept as they are in the state): " + ", ".join(differ))
    return 0


def migrate(ws, dry):
    ws = hat.norm(ws)
    conf_path = os.path.join(ws, ".orchestrator", "orchestrator.conf")
    conf = read(conf_path) if os.path.isfile(conf_path) else ""
    m = re.search(r'^TEMPLATE_VERSION="?(\d+\.\d+\.\d+)"?', conf, re.M)
    if not m:
        return fail("%s is not a workspace with hat's per-project layer (no .orchestrator/orchestrator.conf with a "
                    "TEMPLATE_VERSION)" % ws)
    version = m.group(1)
    if at_version(version, "AGENTS.md") is None:
        return fail("no tag v%s in %s: git fetch --tags there first" % (version, CLONE))
    if os.path.isdir(os.path.join(ws, ".git")):
        dirty = subprocess.run(["git", "-C", ws, "status", "--porcelain", "--"]
                               + [p for p in LAYER if os.path.exists(os.path.join(ws, p))],
                               capture_output=True, encoding="utf-8").stdout.strip()
        if dirty:
            return fail("uncommitted changes in the orchestration layer: commit them first\n" + dirty)
    hit = hat.resolve(ws)
    if hit and hit[1] == ws and os.path.isfile(os.path.join(hat.state(hit[0]), "migrated.json")):
        return fail("%s is already migrated (%s)" % (ws, hat.state(hit[0])))
    if hit and hit[1] != ws:
        return fail("%s is inside the registered project %s" % (ws, hit[0]))
    rules, overrides, checklist, must = plan(ws, version)
    missing = [p for p in must if p.strip() not in rules]
    if missing:
        return fail("verification failed, nothing written: %d project paragraph(s) not saved, first: %s"
                    % (len(missing), missing[0].strip()[:80]))
    pid = hit[0] if hit else hat.project_id(ws)
    memory = sorted(f for f in os.listdir(os.path.join(ws, "memory")) if f.endswith(".md")) \
        if os.path.isdir(os.path.join(ws, "memory")) else []
    tasks_dir = os.path.join(ws, "odd", "tasks")
    tasks = sorted(f for f in os.listdir(tasks_dir) if f.endswith(".md")) if os.path.isdir(tasks_dir) else []
    db = os.path.join(ws, ".orchestrator", "telemetry", "telemetry.db")
    print("hat migrate %s -> %s (template v%s)" % (ws, hat.norm(hat.state(pid)), version))
    print("  config        from .orchestrator/orchestrator.conf")
    print("  memory/       %d files · tasks/ %d files · telemetry %s" % (len(memory), len(tasks),
                                                                        "yes" if os.path.isfile(db) else "none"))
    print("  rules.md      %d project paragraphs, verbatim (review it with the user)" % len(must))
    print("  overrides/    %s" % (", ".join(sorted(overrides)) or "none"))
    print("  checklist.md  %s" % ("the workspace's own" if checklist else "hat's default"))
    print("  migrated-layer/  a full copy of the layer")
    if dry:
        print("(dry run: nothing written)")
        return 0
    if not hit:
        if hat.add(ws) != 0:
            return 1
    st = hat.state(pid)
    stage = st + ".migrating"
    shutil.rmtree(stage, ignore_errors=True)
    try:
        os.makedirs(stage)
        shutil.copy2(conf_path, os.path.join(stage, "config"))
        move_wrapper(ws, os.path.join(stage, "config"), stage, st)
        copy_state(ws, stage)
        with open(os.path.join(stage, "rules.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(rules)
        if checklist:
            with open(os.path.join(stage, "checklist.md"), "w", encoding="utf-8", newline="") as f:
                f.write(checklist)
        for rel, text in overrides.items():
            p = os.path.join(stage, "overrides", *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        copy_layer(ws, os.path.join(stage, "migrated-layer"))
        for p in must:  # the check, on what was written
            if p.strip() not in read(os.path.join(stage, "rules.md")):
                raise RuntimeError("a project paragraph is missing from rules.md: " + p.strip()[:80])
        with open(os.path.join(stage, "migrated.json"), "w", encoding="utf-8") as f:
            json.dump({"from": ws, "template_version": version, "overrides": sorted(overrides),
                       "project_paragraphs": len(must),
                       "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}, f, indent=2)
        for name in os.listdir(stage):  # into the (new, empty) state folder
            os.replace(os.path.join(stage, name), os.path.join(st, name))
        os.rmdir(stage)
    except Exception as err:
        shutil.rmtree(stage, ignore_errors=True)
        return fail("stopped, nothing moved into %s: %s" % (st, err))
    note = hat.record("%s: migrated from %s (template v%s)" % (pid, ws, version), "projects/" + pid)
    print("verified: every project paragraph is in rules.md; state recorded in hat's home (%s)." % note)
    print("Next: review %s/rules.md with the user. The workspace is unchanged and keeps its own layer until it is "
          "cleaned up." % hat.norm(st))
    return 0


HAT_AGENTS = ("explorer.md", "architect.md")  # and every <repo>-dev.md, generated from the developer template


def strip_hooks(path):
    """Drop the hooks that run the old layer's scripts (.orchestrator/hooks/); keep every other setting. Returns
    True when the file changed; removes it when nothing is left."""
    if not os.path.isfile(path):
        return False
    data = json.loads(read(path))
    hooks = data.get("hooks", {})
    changed = False
    for event in list(hooks):
        groups = []
        for g in hooks[event]:
            kept = [h for h in g.get("hooks", []) if ".orchestrator/hooks/" not in h.get("command", "")]
            changed = changed or len(kept) != len(g.get("hooks", []))
            if kept:
                groups.append(dict(g, hooks=kept))
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    if not hooks:
        data.pop("hooks", None)
    if not changed:
        return False
    rest = {k: v for k, v in data.items() if k != "description"}
    if not rest:
        os.remove(path)
    else:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(data, indent=2) + "\n")
    return True


def removable(ws, path, repos):
    """Only a path of the layer itself: never a link, nothing reached through one, nothing inside an app repo."""
    root = os.path.realpath(ws)
    rel = os.path.relpath(path, ws).replace("\\", "/").split("/")
    for i in range(1, len(rel) + 1):  # no link anywhere on the way
        if os.path.islink(os.path.join(ws, *rel[:i])):
            return False
    real = os.path.realpath(path)
    if not real.startswith(root + os.sep):
        return False
    return not any(real == os.path.realpath(os.path.join(ws, r)) or
                   real.startswith(os.path.realpath(os.path.join(ws, r)) + os.sep) for r in repos if r != ".")


def cleanup(ws):
    ws = hat.norm(ws)
    hit = hat.resolve(ws)
    info = os.path.join(hat.state(hit[0]), "migrated.json") if hit and hit[1] == ws else None
    if not info or not os.path.isfile(info):
        return fail("%s is not migrated: run hat migrate %s first" % (ws, ws))
    if os.path.isdir(os.path.join(ws, ".git")):
        dirty = subprocess.run(["git", "-C", ws, "status", "--porcelain", "--"]
                               + [p for p in LAYER if os.path.exists(os.path.join(ws, p))],
                               capture_output=True, encoding="utf-8").stdout.strip()
        if dirty:
            return fail("uncommitted changes in the orchestration layer: commit them first\n" + dirty)
    copy = os.path.join(hat.state(hit[0]), "migrated-layer")
    def entries(base):
        """{rel: what it is}: a file's text, or a link's target (a link is never followed)."""
        out = {}
        for top in LAYER:
            p = os.path.join(base, top)
            if os.path.islink(p):
                out[top] = "link:" + os.readlink(p)
            elif os.path.isfile(p):
                out[top] = read(p)
            for d, dirs, files in os.walk(p) if os.path.isdir(p) and not os.path.islink(p) else []:
                for name in dirs + files:
                    q = os.path.join(d, name)
                    rel = os.path.relpath(q, base).replace("\\", "/")
                    if os.path.islink(q):
                        out[rel] = "link:" + os.readlink(q)
                    elif name in files:
                        out[rel] = read(q)
        return {r: v for r, v in out.items() if not generated(ws, r) and not r.startswith(SKIP[:2])}
    now, then = entries(ws), entries(copy)
    changed = sorted(r for r in set(now) ^ set(then)) + sorted(r for r in set(now) & set(then) if now[r] != then[r])
    if changed:
        return fail("the layer changed since the migration, so hat's copy is out of date (%s). Nothing removed."
                    % ", ".join(changed[:5]))
    removed, kept = [], []
    conf = read(os.path.join(ws, ".orchestrator", "orchestrator.conf"))
    m = re.search(r'^REPOS="?([^"\n]*)"?', conf, re.M)
    repos = m.group(1).split() if m else []

    def ok(p):
        if removable(ws, p, repos):
            return True
        kept.append(os.path.relpath(p, ws).replace("\\", "/"))
        return False
    for top in ("AGENTS.md", "CLAUDE.md", ".orchestrator", "memory", "odd"):
        p = os.path.join(ws, top)
        if os.path.lexists(p) and not ok(p):
            continue
        if os.path.isdir(p):
            shutil.rmtree(p)
            removed.append(top)
        elif os.path.isfile(p):
            os.remove(p)
            removed.append(top)
    skills = set(os.listdir(os.path.join(CLONE, "templates", "skills")))
    for base in (".agents/skills", ".claude/skills"):
        for name in sorted(skills):
            p = os.path.join(ws, *base.split("/"), name)
            if os.path.lexists(p) and ok(p) and os.path.isdir(p):
                shutil.rmtree(p)
                removed.append("%s/%s" % (base, name))
    for rel in [".claude/workflows/pre-pr-review.js"] + [".claude/agents/" + n for n in HAT_AGENTS]:
        p = os.path.join(ws, *rel.split("/"))
        if os.path.isfile(p) and ok(p):
            os.remove(p)
            removed.append(rel)
    for folder, ext in ((".claude/agents", ".md"), (".codex/agents", ".toml")):
        d = os.path.join(ws, *folder.split("/"))
        for name in sorted(os.listdir(d)) if os.path.isdir(d) and not os.path.islink(d) else []:
            stem = name[: -len(ext)]
            if name.endswith(ext) and (stem in ("explorer", "architect") or re.search(r"[-_]dev$", stem)) \
                    and ok(os.path.join(d, name)):
                os.remove(os.path.join(d, name))
                removed.append("%s/%s" % (folder, name))
    for rel in (".claude/settings.json", ".codex/hooks.json"):
        p = os.path.join(ws, *rel.split("/"))
        if os.path.lexists(p) and ok(p) and strip_hooks(p):
            removed.append(rel + " (hat's hooks)")
    for folder in (".claude/workflows", ".claude/agents", ".claude/skills", ".claude", ".codex/agents", ".codex",
                   ".agents/skills", ".agents"):
        d = os.path.join(ws, *folder.split("/"))
        if os.path.isdir(d) and not os.path.islink(d) and not os.listdir(d):
            os.rmdir(d)
    with open(info, encoding="utf-8") as f:
        data = json.load(f)
    data["cleaned_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(info, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    hat.record("%s: old layer cleaned up in %s" % (hit[0], ws), "projects/" + hit[0])
    if os.path.isdir(os.path.join(ws, ".git")):
        subprocess.run(["git", "-C", ws, "add", "-A", "--"] + [p for p in LAYER], capture_output=True)
        p = subprocess.run(["git", "-C", ws, "commit", "-q", "-m",
                            "chore: move the orchestration layer to hat (%s)" % hat.norm(hat.state(hit[0]))],
                           capture_output=True, encoding="utf-8")
        note = "one commit in %s (git revert undoes it)" % ws if p.returncode == 0 else \
            "not committed: " + (p.stderr or p.stdout).strip()[:200]
    else:
        note = "the workspace isn't a git repo: hat's copy is in %s" % hat.norm(copy)
    print("hat migrate --cleanup: removed %s; %s." % (", ".join(removed), note))
    if kept:
        print("Left alone (a link, or inside an app repo): " + ", ".join(sorted(set(kept))))
    print("The project now runs on hat: new sessions get its header, memory and rules from %s."
          % hat.norm(hat.state(hit[0])))
    return 0


def main(args):
    rest = [a for a in args if a not in ("--dry-run", "--cleanup", "--refresh")]
    if len(rest) != 1:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    if "--refresh" in args:
        return refresh(os.path.abspath(rest[0]))
    if "--cleanup" in args:
        return cleanup(os.path.abspath(rest[0]))
    return migrate(os.path.abspath(rest[0]), "--dry-run" in args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
