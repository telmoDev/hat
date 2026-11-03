"""The shape of an ODD task file, odd/tasks/<feature>.md (odd/README.md), read by memory-check.py and telemetry.py.
Pure: it takes the file's text and returns what it says; the callers read the files.
"""
import re

FENCE = re.compile(r"^```.*?^```", re.S | re.M)
_ROW = re.compile(r"^\|\s*(T\d+)\s*\|.*\|\s*([^|]*?)\s*\|\s*$", re.M)
_RESULT = re.compile(r"→\s*(passed|failed)")
_DATE = re.compile(r"^-\s*(\d{4}-\d{2}-\d{2})\b")


def prose(body):
    """The file without its code blocks (entry-shape examples), line numbers kept."""
    return FENCE.sub(lambda m: "\n" * m.group(0).count("\n"), body)


def sections(body):
    """{heading: its text} for the '## ' sections of a task file, code blocks left out."""
    out, cur = {}, None
    for line in prose(body).splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            out[cur] = []
        elif cur:
            out[cur].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


def task_rows(body):
    """[(T<n>, task, status)] from the Tasks table, in order."""
    rows = []
    for m in _ROW.finditer(sections(body).get("Tasks", "")):
        cells = [c.strip() for c in m.group(0).strip().strip("|").split("|")]
        rows.append((m.group(1), cells[1] if len(cells) > 2 else "", m.group(2)))
    return rows


def evidence(body):
    """The Evidence lines that log a criterion's result, in order: date, tasks, criteria, result, method.
    Only what identifies the check: never the command or its output."""
    out = []
    for line in sections(body).get("Evidence", "").splitlines():
        res = _RESULT.search(line)
        if not res:
            continue
        head = line.split("→")[0]
        date = _DATE.match(line)
        out.append({"date": date.group(1) if date else None, "tasks": re.findall(r"\bT\d+\b", head),
                    "criteria": re.findall(r"\bO\d+\b", head), "result": res.group(1),
                    "method": "command" if "`" in head else "other"})
    return out


def task_state(body):
    """A task file's Status, its tasks' statuses, and (criteria passed, criteria total) from its Evidence."""
    sec = sections(body)
    status = re.search(r"^Status:\s*(\w+)", body, re.M)
    crit = re.search(r"^Criteria:(.*)$", sec.get("Outcome", ""), re.M)
    total = sorted(set(re.findall(r"\bO\d+\b", crit.group(1)))) if crit else []
    latest = {}  # each criterion's last logged result
    for e in evidence(body):
        for o in e["criteria"]:
            latest[o] = e["result"]
    return {
        "status": status.group(1).lower() if status else "",
        "tasks": [(t, st.lower()) for t, _, st in task_rows(body)],
        "evidence": set(re.findall(r"\bT\d+\b", sec.get("Evidence", ""))),
        "passed": sum(1 for o in total if latest.get(o) == "passed"),
        "total": len(total),
    }
