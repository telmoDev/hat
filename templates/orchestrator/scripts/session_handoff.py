#!/usr/bin/env python3
"""Automatic session handoff: where the work stopped, for the next session, when memory/ wasn't synced.
  python3 .orchestrator/scripts/session_handoff.py start < payload   (SessionStart: prints the draft as context)
  python3 .orchestrator/scripts/session_handoff.py end < payload     (SessionEnd: writes the draft)
Hooks call it through .orchestrator/hooks/session-handoff.sh, which never fails the session.

memory/ is written only by the orchestrator (sync-memory). A session closed, killed or compacted without it
leaves the next one to rebuild its context from git. This keeps a short draft instead: per repo the branch,
uncommitted files and commits not in origin/<base>; the active task files it changed, with their Next: and
open tasks; agent runs that started and never finished (from the telemetry store, when there is one). It is shown
once, at the next start, only when memory/ didn't change during that session; the orchestrator offers to reconcile it into memory/.
A session that ends without its end hook (killed, or a tool that has none) is caught by the next start.

Local git only, no network and no model calls. Paths and counts, never file contents, diffs or commit messages;
a line that looks like a secret is left out. State lives in .orchestrator/tmp/handoff/ (git-ignored).
SESSION_HANDOFF="off" in orchestrator.conf turns it off.
"""
import datetime
import glob
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys

MAX_LINES = 10
MAX_ITEM = 80
# The same rule as memory-check.py's SECRET (tests/test_session_handoff.py keeps them equal).
SECRET = re.compile(
    r"((password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S"
    r"|bearer\s+[A-Za-z0-9._~+/-]{16,}"
    r"|BEGIN [A-Z ]*PRIVATE KEY"
    r"|[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}"
    r"|\b(?=(?:[A-Za-z+/_-]*\d){4})[A-Za-z0-9+/_-]{40,}\b)",  # long token with 4+ digits; branch names have none
    re.I,
)
_STATUS = re.compile(r"^Status:\s*(\w+)(?:.*?·\s*Next:\s*(.*))?$", re.M)


def utc(now=None):
    return now or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def conf(root):
    out = {}
    try:
        with open(os.path.join(root, ".orchestrator", "orchestrator.conf"), encoding="utf-8") as f:
            for line in f:
                m = re.match(r'^([A-Z_]+)="?([^"\n]*)"?\s*$', line)
                if m:
                    out[m.group(1)] = m.group(2)
    except OSError:
        pass
    return out


def state_dir(root):
    return os.path.join(root, ".orchestrator", "tmp", "handoff")


def memory_hash(root):
    """What sync-memory changes: the memory files' contents."""
    digest = hashlib.sha256()
    for p in sorted(glob.glob(os.path.join(root, "memory", "*.md"))):
        with open(p, "rb") as f:
            digest.update(os.path.basename(p).encode() + b"\0" + f.read() + b"\0")
    return digest.hexdigest()


def _git(repo, *args):
    p = subprocess.run(["git", "-C", repo] + list(args), capture_output=True, timeout=5)
    return p.stdout.decode("utf-8", "replace").strip() if p.returncode == 0 else None


def _short(s):
    s = " ".join(s.split())
    return s if len(s) <= MAX_ITEM else s[:MAX_ITEM - 1] + "…"


def repo_lines(root, cfg):
    bases = dict(b.split("=", 1) for b in cfg.get("BASE_BRANCHES", "").split() if "=" in b)
    out = []
    for name in cfg.get("REPOS", ".").split():
        repo = root if name == "." else os.path.join(root, name)
        branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        if branch is None:
            continue
        base = bases.get(name, "main")
        dirty = [line[3:] for line in (_git(repo, "status", "--porcelain") or "").splitlines() if line.strip()]
        ahead = _git(repo, "rev-list", "--count", "origin/%s..HEAD" % base)
        ahead = int(ahead) if ahead and ahead.isdigit() else 0
        if not dirty and not ahead and branch == base:
            continue
        label = os.path.basename(root) if name == "." else name
        parts = ["%s: on %s" % (label, branch)]
        if dirty:
            shown = ", ".join(_short(p) for p in dirty[:3]) + (", …" if len(dirty) > 3 else "")
            parts.append("%d uncommitted (%s)" % (len(dirty), shown))
        if ahead:
            parts.append("%d commit%s not in origin/%s" % (ahead, "" if ahead == 1 else "s", base))
        out.append(" · ".join(parts))
    return out


def task_hashes(root):
    out = {}
    for p in glob.glob(os.path.join(root, "odd", "tasks", "*.md")):
        with open(p, "rb") as f:
            out[os.path.basename(p)] = hashlib.sha256(f.read()).hexdigest()
    return out


def task_lines(root, before=None):
    """The active task files this session changed (all of them when its start didn't record them), and a count
    of the others, which memory/ already tracks."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import odd_tasks  # next to this file
    out, unchanged = [], 0
    for p in sorted(glob.glob(os.path.join(root, "odd", "tasks", "*.md"))):
        with open(p, encoding="utf-8") as f:
            body = f.read()
        m = _STATUS.search(body)
        if not m or m.group(1).lower() != "active":
            continue
        name = os.path.basename(p)
        if before is not None and before.get(name) == hashlib.sha256(body.encode("utf-8")).hexdigest():
            unchanged += 1
            continue
        open_ = [tid for tid, _, status in odd_tasks.task_rows(body) if status.lower() != "done"]
        parts = ["odd/tasks/" + os.path.basename(p)]
        if m.group(2):
            parts.append("Next: " + _short(m.group(2)))
        if open_:
            parts.append("open: " + ", ".join(open_))
        out.append(" · ".join(parts))
    return out, unchanged


def agent_line(root, sid):
    db = os.path.join(root, ".orchestrator", "telemetry", "telemetry.db")
    if not os.path.isfile(db):
        return []
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True, timeout=1)
        try:
            types = [r[0] or "?" for r in con.execute(
                "SELECT agent_type FROM agent_invocations WHERE run_id = ? AND finished_at IS NULL "
                "AND agent_type IS NOT 'main' ORDER BY started_at", ("claude:" + sid,))]
        finally:
            con.close()
    except sqlite3.Error:
        return []
    if not types:
        return []
    return ["agent runs started and not finished: %d (%s)" % (len(types), ", ".join(sorted(set(types))))]


def draft(root, sid, ended_at, how, before=None):
    cfg = conf(root)
    tasks, unchanged = task_lines(root, before)
    lines = repo_lines(root, cfg) + tasks + agent_line(root, sid)
    if not lines:
        return None
    if unchanged:
        lines.append("%d other active task file%s unchanged this session" % (unchanged, "" if unchanged == 1 else "s"))
    kept = []
    for line in lines[:MAX_LINES]:
        kept.append("- (a line was left out: it looked like a secret)" if SECRET.search(line) else "- " + line)
    if len(lines) > MAX_LINES:
        kept.append("- … and %d more" % (len(lines) - MAX_LINES))
    return ("Session handoff: the last session (%s, %s %s) didn't update memory/, so where it stopped wasn't saved. "
            "From git and the task files:\n%s\nOffer the user, in one line, to reconcile this into memory/ with "
            "sync-memory before anything else; check it against git first."
            % (sid[:8], how, ended_at, "\n".join(kept)))


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _close(root, sid, started, now, how):
    """Write the last session's draft: none when memory/ changed since its start."""
    synced = started is not None and started.get("memory") != memory_hash(root)
    text = None if synced else draft(root, sid, now, how, (started or {}).get("tasks"))
    _write(os.path.join(state_dir(root), "last.json"),
           {"session_id": sid, "ended_at": now, "synced": synced, "shown": text is None, "text": text})


def _session_id(payload, now):
    sid = payload.get("session_id") if isinstance(payload, dict) else None
    return sid if isinstance(sid, str) and re.fullmatch(r"[\w.-]{1,128}", sid) else "session-" + re.sub(r"\D", "", now)


def end(root, payload, now=None):
    if conf(root).get("SESSION_HANDOFF", "on") == "off":
        return
    now = utc(now)
    sid = _session_id(payload, now)
    path = os.path.join(state_dir(root), sid + ".start.json")
    _close(root, sid, _read(path), now, "ended")
    if os.path.exists(path):
        os.remove(path)


def start(root, payload, now=None):
    """The draft to show (once), or None. Records this session's start."""
    if conf(root).get("SESSION_HANDOFF", "on") == "off":
        return None
    now = utc(now)
    sid = _session_id(payload, now)
    d = state_dir(root)
    # Sessions that started and haven't ended: killed, a tool with no end hook, or one still open in parallel. Each
    # is read once (the oldest first, the last one wins) and its start is kept, so if it is still open its own end
    # judges it later. Starts read more than a week ago are dropped.
    week_ago = (datetime.datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ")
                - datetime.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    others = [(s, p) for p in glob.glob(os.path.join(d, "*.start.json"))
              for s in [_read(p)] if os.path.basename(p) != sid + ".start.json"]
    for s, p in sorted(others, key=lambda x: (x[0] or {}).get("started_at", "")):
        if not s or s.get("read_at", now) < week_ago:
            os.remove(p)
        elif not s.get("read_at"):
            _close(root, s.get("session_id", "?"), s, now, "still open or ended without its end hook; seen")
            _write(p, dict(s, read_at=now))
    last = _read(os.path.join(d, "last.json"))
    text = None
    if last and not last.get("shown") and last.get("text"):
        text = last["text"]
        _write(os.path.join(d, "last.json"), dict(last, shown=True))
    mine = os.path.join(d, sid + ".start.json")
    if not os.path.exists(mine):  # a resumed or compacted session keeps its first start
        _write(mine, {"session_id": sid, "started_at": now, "memory": memory_hash(root), "tasks": task_hashes(root)})
    return text


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    if len(argv) > 1 and argv[1] == "end":
        end(root, payload)
    elif len(argv) > 1 and argv[1] == "start":
        text = start(root, payload)
        if text:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))


if __name__ == "__main__":
    try:
        main(sys.argv)
    except Exception as err:  # never fail the session: note it next to the state
        try:
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            os.makedirs(state_dir(root), exist_ok=True)
            with open(os.path.join(state_dir(root), "errors.log"), "a") as f:
                f.write("%s %s: %s\n" % (utc(), type(err).__name__, str(err)[:200].replace("\n", " ")))
        except Exception:
            pass
