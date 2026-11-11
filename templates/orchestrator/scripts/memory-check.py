#!/usr/bin/env python3
"""/sync-memory step 3: refuse a memory that git contradicts.

Fails (exit 1) on: a repeated line within a section; a PR reference that does not exist; an
In flight PRs cell that calls a PR open/draft/merged/closed when GitHub disagrees; an open PR
missing from the In flight table; a commit hash in In flight; a "done" entry in PROGRESS; a
DECISIONS entry with no Until line, or whose Until PR is merged/closed or whose Until date is past;
anything that looks like a secret or an email address, in memory/ or a task file (odd/tasks/*.md);
a PROGRESS "Doc:" line naming a task file that does not exist, or one whose Status is done; a task
file task marked done with no Evidence line naming it, or a done task file with tasks not done; an
In flight "N/M passed" cell that the linked task file contradicts; the four files over the word
budget; an AGENTS.md longer than Codex reads (project_doc_max_bytes in .codex/config.toml).
Warns on: PR checks skipped (no gh or no remote).
Repos come from .orchestrator/orchestrator.conf.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

from odd_tasks import prose, task_state  # the task-file shape, shared with telemetry.py

import layout  # noqa: E402  next to this file: where the project's files are

ROOT = layout.root(__file__)
LAYOUT = layout.of(ROOT)
MEM = LAYOUT.memory
BASE = os.path.dirname(MEM)  # task links in the memory are relative to it: odd/tasks/… in a workspace, tasks/… in hat's state
FILES = ["PROJECT_STATE.md", "PROGRESS.md", "DECISIONS.md", "NEXT_STEPS.md"]
TASKS = LAYOUT.tasks


def conf():
    values = {}
    with open(LAYOUT.conf) as fh:
        for line in fh:
            m = re.match(r'\s*([A-Z_]+)=["\']?(.*?)["\']?\s*$', line)
            if m:
                values[m.group(1)] = m.group(2)
    return values


CONF = conf()
REPOS = CONF.get("REPOS", ".").split()
LABEL = {r: (os.path.basename(ROOT) if r == "." else r) for r in REPOS}
WORD_BUDGET = int(CONF.get("WORD_BUDGET", "900"))
# Values, not words: "no secrets in memory" is fine, "secret: abc123" is not.
SECRET = re.compile(
    r"((password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S"
    r"|bearer\s+[A-Za-z0-9._~+/-]{16,}"
    r"|BEGIN [A-Z ]*PRIVATE KEY"
    r"|[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}"
    # long token with 4+ digits; a lowercase slug (a branch name like support-january-2026-…) is not one
    r"|(?<![A-Za-z0-9+/_-])(?!(?-i:[a-z0-9]+(?:[-_][a-z0-9]+)+)\b)(?=(?:[A-Za-z+/_-]*\d){4})[A-Za-z0-9+/_-]{40,}\b)",
    re.I,
)
GENERATED = re.compile(r"<!-- state:begin.*?<!-- state:end -->", re.S)
INLINE = re.compile(r"`[^`\n]*`")


def literals_out(line):
    """The line without its inline code spans (formats and examples such as `api #12 open`)."""
    return INLINE.sub(" ", line)
REPO_WORD = re.compile(r"(?<![\w-])(" + "|".join(re.escape(LABEL[r]) for r in REPOS) + r")(?![\w-])")

errors, warnings = [], []


def prs(repo):
    path = os.path.join(ROOT, repo)
    has_remote = subprocess.run(["git", "-C", path, "remote", "get-url", "origin"], capture_output=True).returncode == 0
    if not shutil.which("gh") or not has_remote:
        return None
    res = subprocess.run(
        ["gh", "pr", "list", "--state", "all", "--limit", "200", "--json", "number,state,isDraft"],
        cwd=path, capture_output=True, text=True,
    )
    if res.returncode != 0:
        return None
    return {p["number"]: p for p in json.loads(res.stdout)}


gh = {}
for r in REPOS:
    found = prs(r)
    if found is None:
        warnings.append(f"PR checks skipped for {LABEL[r]} (no gh, no remote, or gh failed)")
    else:
        gh[LABEL[r]] = found
text = {f: open(os.path.join(MEM, f)).read() for f in FILES if os.path.exists(os.path.join(MEM, f))}
tasks = {}
if os.path.isdir(TASKS):
    for t in sorted(os.listdir(TASKS)):
        if t.endswith(".md"):
            with open(os.path.join(TASKS, t), encoding="utf-8") as fh:
                tasks[LAYOUT.task_prefix + t] = fh.read()


state_of = {f: task_state(b) for f, b in tasks.items()}


def actual(pr):
    if pr["state"] == "MERGED":
        return "merged"
    if pr["state"] == "CLOSED":
        return "closed"
    return "draft" if pr["isDraft"] else "open"


# 1. Repeated lines within one section (tables' separator rows and code fences excepted).
for f, body in text.items():
    seen = {}
    for n, line in enumerate(GENERATED.sub("", body).splitlines(), 1):
        s = line.strip()
        if s.startswith("## "):
            seen = {}
        if not s or s.startswith("|---") or s.startswith("```"):
            continue
        if s in seen:
            errors.append(f"{f}:{n}: repeats line {seen[s]}: {s[:70]}")
        else:
            seen[s] = n

# 2. Every PR reference exists in a repo named on its line (in any checked repo if none is named).
# Code blocks and inline code are examples and formats, not references.
for f, body in text.items():
    for n, line in enumerate(prose(GENERATED.sub("", body)).splitlines(), 1):
        line = literals_out(line)
        named = [r for r in sorted(set(REPO_WORD.findall(line))) if r in gh]
        where = named or list(gh)
        if not where:
            continue
        for num_s in re.findall(r"#(\d+)\b", line):
            if not any(int(num_s) in gh[r] for r in where):
                errors.append(f"{f}:{n}: #{num_s} is not a PR in {' or '.join(where)}")

# 3. In flight agrees with GitHub (each `<repo> #N <state>` exists and has that state), and covers every open PR.
state = text.get("PROJECT_STATE.md", "")
m = re.search(r"^## In flight\n(.*?)(?=^## |\Z)", GENERATED.sub("", state), re.S | re.M)
listed = {r: set() for r in gh}
if m:
    rows = [l for l in m.group(1).splitlines() if l.startswith("|") and not l.startswith("|---")]
    single = LABEL[REPOS[0]] if len(REPOS) == 1 else None
    for row in rows[1:]:
        current = single
        for tok in re.finditer(REPO_WORD.pattern + r"|#(\d+)\s*(open|draft|merged|closed)?", row):
            if tok.group(1):
                current = tok.group(1)
                continue
            if not current or current not in gh:
                continue
            num, word = int(tok.group(2)), tok.group(3)
            listed[current].add(num)
            pr = gh[current].get(num)
            if not pr:  # check 2 skips inline code, and the PRs cell is often written in it
                errors.append(f"PROJECT_STATE.md In flight: {current} #{num} is not a PR")
            elif word and word != actual(pr):
                errors.append(f"PROJECT_STATE.md In flight: {current} #{num} says '{word}', GitHub says '{actual(pr)}'")
else:
    errors.append("PROJECT_STATE.md: no '## In flight' section")
for repo, found in gh.items():
    for num, pr in found.items():
        if pr["state"] == "OPEN" and num not in listed[repo]:
            errors.append(f"PROJECT_STATE.md In flight: open PR {repo} #{num} is missing")

# 3b. In flight holds no commit hashes: they go stale on the next push, and the generated block has the branches.
if m:
    for row in m.group(1).splitlines():
        if row.startswith("|") and re.search(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b", row):
            errors.append(f"PROJECT_STATE.md In flight: drop the commit hash, it goes stale: {row.strip()[:70]}")

# 3c. PROGRESS holds only partial tasks: a done task's record is its PR and the memory's git history.
for n, line in enumerate(prose(text.get("PROGRESS.md", "")).splitlines(), 1):
    if line.startswith("## ") and re.search(r"[—-]\s*done\b", line, re.I):
        errors.append(f"PROGRESS.md:{n}: done tasks leave PROGRESS (their PR keeps the record): {line[:70]}")

# 3d. Every DECISIONS entry is temporary and says until when; an expired one is deleted.
today = datetime.date.today().isoformat()
for entry in re.split(r"^(?=## )", prose(text.get("DECISIONS.md", "")), flags=re.M):
    if not entry.startswith("## "):
        continue
    title = entry.splitlines()[0][3:73]
    until = re.search(r"^Until:\s*(.+)$", entry, re.M | re.I)
    if not until:
        errors.append(f"DECISIONS.md '{title}': no 'Until:' line. A lasting rule goes to AGENTS.md › Workspace rules")
        continue
    u = until.group(1)
    for d in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", u):
        if d < today:
            errors.append(f"DECISIONS.md '{title}': Until {d} has passed, delete the entry")
    # Only a PR whose repo is certain: named on the line, or the only repo checked.
    named = [r for r in sorted(set(REPO_WORD.findall(u))) if r in gh] or (list(gh) if len(gh) == 1 else [])
    for num_s in re.findall(r"#(\d+)\b", u):
        for r in named:
            pr = gh[r].get(int(num_s))
            if pr and actual(pr) in ("merged", "closed"):
                errors.append(f"DECISIONS.md '{title}': Until {r} #{num_s}, which is {actual(pr)}, delete the entry")

# 3e. A task is done only with evidence, and a task file is done only when all its tasks are.
for f, st in state_of.items():
    for tid, status in st["tasks"]:
        if status.startswith("done") and tid not in st["evidence"]:
            errors.append(f"{f}: {tid} is done with no evidence: log its check under Evidence or set it back to pending")
        if st["status"] == "done" and not status.startswith("done"):
            errors.append(f"{f}: Status: done but {tid} is {status}")

# 3f. A PROGRESS "Doc:" line names a task file that exists and is not done.
for n, line in enumerate(prose(text.get("PROGRESS.md", "")).splitlines(), 1):
    doc = re.match(r"Doc:\s*`?([^`\s]+)", line)
    if not doc:
        continue
    if not os.path.isfile(os.path.join(BASE, doc.group(1))):
        errors.append(f"PROGRESS.md:{n}: no such task file: {doc.group(1)}")
    elif state_of.get(doc.group(1), {}).get("status") == "done":
        errors.append(f"PROGRESS.md:{n}: {doc.group(1)} is done but PROGRESS still lists it")

# 3g. An In flight row that links a task file agrees with it on the criteria passed.
if m:
    for row in m.group(1).splitlines():
        doc = re.search(r"(" + re.escape(LAYOUT.task_prefix) + r"[^\s|`)\]]+\.md)", row)
        if not row.startswith("|") or not doc:
            continue
        st = state_of.get(doc.group(1))
        if st is None:
            errors.append(f"PROJECT_STATE.md In flight: no such task file: {doc.group(1)}")
            continue
        cell = re.search(r"(\d+)/(\d+) passed", row)
        if cell and (int(cell.group(1)), int(cell.group(2))) != (st["passed"], st["total"]):
            errors.append(f"PROJECT_STATE.md In flight: says {cell.group(0)}, the task file has {st['passed']}/{st['total']} passed ({doc.group(1)})")

# 4. Secrets and personal data, in the memory and in the task files (committed with it).
for f, body in list(text.items()) + list(tasks.items()):
    for n, line in enumerate(body.splitlines(), 1):
        if SECRET.search(line):
            errors.append(f"{f}:{n}: looks like a secret or an email: {line.strip()[:70]}")

# 5. Size.
words = sum(len(GENERATED.sub("", b).split()) for b in text.values())
if words > WORD_BUDGET:
    errors.append(f"memory is {words} words (budget {WORD_BUDGET}): trim PROGRESS first, then DECISIONS")

# 6. Codex reads only the first project_doc_max_bytes of AGENTS.md: past it, the end of the guide is lost.
codex_cfg, guide = os.path.join(ROOT, ".codex", "config.toml"), os.path.join(ROOT, "AGENTS.md")
if not os.environ.get("HAT_STATE") and os.path.exists(codex_cfg) and os.path.exists(guide):
    with open(codex_cfg, encoding="utf-8") as fh:
        lim = re.search(r"^project_doc_max_bytes\s*=\s*(\d+)", fh.read(), re.M)
    limit, size = int(lim.group(1)) if lim else 32768, os.path.getsize(guide)
    if size > limit:
        errors.append(f"AGENTS.md is {size} bytes; Codex reads only {limit} (project_doc_max_bytes in .codex/config.toml): trim it or raise the limit")
    elif size > limit * 0.85:
        warnings.append(f"AGENTS.md is {size} bytes, near the {limit} Codex reads: trim it before it grows")

for w in warnings:
    print("warn:", w)
for e in errors:
    print("FAIL:", e)
print(f"memory-check: {len(errors)} error(s), {len(warnings)} warning(s), {words} words")
sys.exit(1 if errors else 0)
