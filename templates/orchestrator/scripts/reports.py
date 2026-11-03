"""Usage, metrics and run reports over the local telemetry store, as Markdown. Read-only: no writes, no network,
no model calls. Called by `telemetry.py usage | metrics | report`.

Definitions (what each figure means and what it never stands for):
- Delegation: an agent run that started (it has an agent id). A failed launch never started and counts apart.
- Finished: a delegation that stopped (completed or failed). Running ones are "in progress" while their run is
  open and "unfinished" once it closed; they count neither as successes nor as failures.
- Succeeded: finished without a runtime error, shown as n/m. It says nothing about whether the work is right:
  the criteria say that. 0/0 is "no data", never 100%.
- Retry: a new run of the same task by the same agent after a failed one. Re-invocation: any repeat of the same
  task by the same agent (review rounds included), whatever the earlier result.
- Coverage: finished delegations with runtime_reported usage over finished delegations. A finished one without
  usage counts in coverage but adds no tokens: its tokens are "—" (not available), never 0.
- Tokens are added up only for runtimes whose usage semantics are verified (Claude Code: input excludes cache).
- A run is a session. One that launched no agent still counts where runs can be grouped (runtime, project, run)
  and is reported apart where they can't (agent, model, task); agent-level filters leave it out.
- Run wall time comes from the run's start and end. Cumulative agent time adds up agents that ran in parallel,
  so it is never wall time.
- Efficiency and cost per task need every task of the aggregate fully covered (all its delegations finished,
  with usage); otherwise "incomplete", never an average of the covered part.
- Criteria come from the task files and are not attributed to runs. A task without criteria is not a failed one.
- The API-equivalent cost is an estimate (api_cost.py), never what a subscription costs.
"""
import datetime
import statistics
from decimal import Decimal

import api_cost

VERIFIED = {"claude-code"}
DIMENSIONS = {"agent": ("Agent", "agent_type"), "model": ("Model", "model"), "runtime": ("Runtime", "runtime"),
              "project": ("Project", "project_id"), "task": ("Task", "task_id"), "run": ("Run", "run_id")}
TOKENS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
NA = "—"
_CENT = Decimal("0.0001")


def _iso(v):
    """A date or ISO 8601 timestamp as the store writes them (UTC, milliseconds)."""
    if len(v) == 10:
        v += "T00:00:00Z"
    d = datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    d = d.astimezone(datetime.timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (d.microsecond // 1000)


def _load(db):
    """Every agent run with its run, usage and derived states."""
    usage = {}
    for inv, source, *tokens in db.execute("SELECT invocation_id, source, " + ", ".join(TOKENS) +
                                           " FROM usage_records"):
        u = usage.setdefault(inv, {"reported": False, "tokens": dict.fromkeys(TOKENS, 0)})
        if source == "runtime_reported":
            u["reported"] = True
            for k, v in zip(TOKENS, tokens):
                u["tokens"][k] += v or 0
    rows = db.execute(
        "SELECT i.invocation_id, i.run_id, r.project_id, coalesce(i.runtime, r.runtime), i.model, i.agent_type, "
        "i.task_id, i.agent_id, i.status, i.started_at, i.duration_ms, i.retry_number, i.parent_invocation_id, "
        "r.finished_at, r.total_duration_ms, r.status FROM agent_invocations i "
        "LEFT JOIN runs r ON r.run_id = i.run_id").fetchall()
    status_of = {r[0]: r[8] for r in rows}
    out = []
    for (inv, run, project, runtime, model, agent, task, agent_id, status, started, dur, retry, parent,
         run_end, run_ms, run_status) in rows:
        deleg = agent_id is not None
        finished = deleg and status in ("completed", "success", "failed")
        running = deleg and not finished
        u = usage.get(inv)
        covered = finished and bool(u and u["reported"])
        out.append({
            "id": inv, "short": agent_id or inv.split(":")[-1], "run_id": run, "project_id": project,
            "runtime": runtime, "model": model, "agent_type": agent, "task_id": task, "status": status,
            "started": started or "", "duration": dur, "deleg": deleg, "failed_launch": not deleg and status == "failed",
            "finished": finished, "succeeded": finished and status in ("completed", "success"),
            "in_progress": running and not run_end, "unfinished": running and bool(run_end),
            "covered": covered, "tokens": u["tokens"] if covered and runtime in VERIFIED else None,
            "unverified": covered and runtime not in VERIFIED,
            "reinvocation": (retry or 0) > 0, "retry": (retry or 0) > 0 and status_of.get(parent) == "failed",
            "run_end": run_end, "run_ms": run_ms, "run_status": run_status})
    return out


_AGENT_FILTERS = ("model", "agent", "task", "status")


def _filter(rows, f, keys=None):
    keys = keys or {"project": "project_id", "runtime": "runtime", "model": "model", "agent": "agent_type",
                    "task": "task_id", "status": "status"}
    since, until = f.get("since"), f.get("until")
    since, until = since and _iso(since), until and _iso(until)
    return [r for r in rows
            if all(r[col] == f[k] for k, col in keys.items() if f.get(k))
            and (not since or r["started"] >= since) and (not until or r["started"] < until)]


def _runs_without_agents(db, f):
    """The runs that match the run-level filters and launched no agent."""
    runs = [{"run_id": r[0], "project_id": r[1], "runtime": r[2], "started": r[3] or "", "run_ms": r[4]}
            for r in db.execute("SELECT run_id, project_id, runtime, started_at, total_duration_ms FROM runs "
                                "WHERE run_id NOT IN (SELECT run_id FROM agent_invocations WHERE run_id IS NOT NULL)")]
    return _filter(runs, f, {"project": "project_id", "runtime": "runtime"})


def _groups(rows, by):
    out = {}
    for r in rows:
        if by is None:
            key = "%s · %s" % (r["agent_type"] or NA, r["model"] or NA)
        else:
            key = r[DIMENSIONS[by][1]] or NA
        out.setdefault(key, []).append(r)
    return sorted(out.items())


def _n(v):
    return NA if v is None else "{:,}".format(v)


def _secs(ms):
    return NA if ms is None else "%.1f s" % (ms / 1000.0)


def _ratio(n, m):
    return "%d/%d (no data)" % (n, m) if not m else "%d/%d (%d%%)" % (n, m, round(100.0 * n / m))


def _p95(values):
    s = sorted(values)
    return s[max(0, -(-95 * len(s) // 100) - 1)]


def _sum_tokens(rows):
    """Token sums over the rows that have them, or None when none has (not available, not zero)."""
    have = [r["tokens"] for r in rows if r["tokens"] is not None]
    if not have:
        return None
    return {k: sum(t[k] for t in have) for k in TOKENS}


def usage(db, f, by):
    rows = [r for r in _filter(_load(db), f) if r["deleg"]]
    if not rows:
        return "No agent runs match these filters.\n"
    label = "Agent · model" if by is None else DIMENSIONS[by][0]
    out = ["## Usage", "", "> Tokens as the runtime reported them. `—` is not available, never zero. Coverage: "
           "finished agent runs with reported usage over finished agent runs.", "",
           "| %s | Invocations | Coverage | Input | Output | Cache read | Cache write | Total |" % label,
           "|---|---|---|---|---|---|---|---|"]
    for key, g in _groups(rows, by):
        tok = _sum_tokens(g)
        cells = [NA] * 5 if tok is None else [_n(tok[k]) for k in TOKENS] + [_n(sum(tok.values()))]
        out.append("| %s | %d | %d/%d | %s |" % (key, len(g), sum(r["covered"] for r in g),
                                                 sum(r["finished"] for r in g), " | ".join(cells)))
    unverified = sorted({r["runtime"] or "unknown" for r in rows if r["unverified"]})
    if unverified:
        out += ["", "> %s: usage semantics not verified, so its tokens are not added up or compared."
                % ", ".join(unverified)]
    return "\n".join(out) + "\n"


def _criteria(db):
    crit, status = {}, dict(db.execute("SELECT task_id, status FROM tasks"))
    for task, code, st in db.execute("SELECT task_id, criterion_code, status FROM criteria ORDER BY criterion_code"):
        crit.setdefault(task, []).append((code, st))
    return crit, status


def _cost(rows, rates):
    """Sum of the estimates over rows, (currency, Decimal), or a reason it can't be given."""
    if not rates:
        return None, "no rates"
    total, currency = Decimal(0), None
    for r in rows:
        if r["tokens"] is None:
            continue
        rate = api_cost.rate_for(rates, api_cost.PROVIDER.get(r["runtime"]), r["model"], r["started"][:10])
        cost, why = api_cost.estimate(r["runtime"], dict(r["tokens"], source="runtime_reported"), rate)
        if cost is None:
            return None, "not priced: " + why
        if currency not in (None, rate["currency"]):
            return None, "mixed currencies"
        total, currency = total + cost, rate["currency"]
    return (currency, total), None


def metrics(db, f, by, rates_path):
    rows = _filter(_load(db), f)
    by = by or "runtime"
    agent_filtered = any(f.get(k) for k in _AGENT_FILTERS)
    empty_runs = [] if agent_filtered else _runs_without_agents(db, f)
    if agent_filtered and not rows:
        return "No agent runs match these filters.\n"
    if not rows and not empty_runs:
        return "No runs match these filters.\n"
    label = DIMENSIONS[by][0]
    groupable = by in ("runtime", "project", "run")
    extra = {}
    for r in empty_runs if groupable else []:
        extra.setdefault(r[DIMENSIONS[by][1]] or NA, {})[r["run_id"]] = r["run_ms"]
    groups = dict(_groups(rows, by))
    for key in extra:
        groups.setdefault(key, [])
    crit, task_status = _criteria(db)
    rates, _, _ = api_cost.load_rates(rates_path)
    perf, qual, eff = [], [], []
    for key, g in sorted(groups.items()):
        runs = {r["run_id"]: r["run_ms"] for r in g}
        runs.update(extra.get(key, {}))
        walls = [ms for ms in runs.values() if ms is not None]
        deleg = [r for r in g if r["deleg"]]
        fin = [r for r in deleg if r["finished"]]
        durs = [r["duration"] for r in fin if r["duration"] is not None]
        perf.append("| %s | %d | %s | %d | %d | %d | %d | %s | %d | %d | %s | %s |" % (
            key, len(runs), _secs(statistics.median(walls)) if walls else NA, len(deleg),
            sum(r["failed_launch"] for r in g), sum(r["in_progress"] for r in g), sum(r["unfinished"] for r in g),
            _ratio(sum(r["succeeded"] for r in fin), len(fin)), sum(r["retry"] for r in deleg),
            sum(r["reinvocation"] for r in deleg), _secs(statistics.median(durs)) if durs else NA,
            _secs(sum(durs)) if durs else NA))
        tasks = sorted({r["task_id"] for r in g if r["task_id"]})
        with_crit = [tk for tk in tasks if tk in crit]
        states = [st for tk in with_crit for _, st in crit[tk]]
        done = [tk for tk in tasks if task_status.get(tk) == "done"]
        qual.append("| %s | %d | %d | %d | %d | %d | %d | %d |" % (
            key, len(tasks), len(with_crit), len(tasks) - len(with_crit), states.count("passed"),
            states.count("failed"), len(done), sum(task_status.get(tk) == "blocked" for tk in tasks)))
        by_task = {tk: [r for r in deleg if r["task_id"] == tk] for tk in tasks}
        covered = [tk for tk in tasks if by_task[tk] and all(r["finished"] and r["tokens"] is not None
                                                             for r in by_task[tk])]
        complete = bool(tasks) and len(covered) == len(tasks)
        task_rows = [r for tk in tasks for r in by_task[tk]]
        tok = _sum_tokens(task_rows)
        total = sum(tok.values()) if tok else None
        if not tasks:
            per_done = per_passed = cost = NA
        elif not complete:
            per_done = per_passed = cost = "incomplete"
        else:
            done_tok = _sum_tokens([r for tk in done for r in by_task[tk]])
            per_done = _n(sum(done_tok.values()) // len(done)) if done and done_tok else NA
            passed = states.count("passed")
            per_passed = _n(total // passed) if passed and total is not None else NA
            value, why = _cost(task_rows, rates)
            cost = why if value is None else "%s %s" % (value[0], (value[1] / len(tasks)).quantize(_CENT))
        retries = sum(r["retry"] for r in deleg)
        eff.append("| %s | %d/%d | %d/%d | %s | %s | %s | %s |" % (
            key, sum(r["covered"] for r in fin), len(fin), len(covered), len(tasks), per_done, per_passed,
            "%.2f" % (retries / float(len(tasks))) if tasks else NA, cost))
    out = ["## Performance", "",
           "| %s | Runs | Run wall time (median) | Delegations | Failed launches | In progress | Unfinished | "
           "Succeeded | Retries | Re-invocations | Agent time (median) | Agent time (cumulative) |" % label,
           "|---|---|---|---|---|---|---|---|---|---|---|---|"] + perf + [
           "", _runs_note(rows, empty_runs, groupable, agent_filtered, db, f),
           "", "> Succeeded: finished without a runtime error, not that the work is right (the criteria say that). "
           "Retries follow a failed run of the same task and agent; re-invocations are any repeat. The "
           "cumulative agent time adds up agents that ran in parallel, so it is not wall time.", "",
           "## Quality", "",
           "| %s | Tasks | With criteria | Without criteria | Criteria passed | Criteria failed | Tasks done | "
           "Tasks blocked |" % label, "|---|---|---|---|---|---|---|---|"] + qual + [
           "", "> Criteria come from the task files and are not attributed to runs. A task without criteria is not "
           "a failed one.", "",
           "## Efficiency", "",
           "| %s | Coverage | Tasks covered | Tokens per task done | Tokens per criterion passed | Retries per task | "
           "API-equivalent per task (estimated) |" % label, "|---|---|---|---|---|---|---|"] + eff + [
           "", "> Shown only when every task of the row is fully covered; otherwise incomplete. The cost is "
           "API-equivalent (estimated, combined cache-write rate) at the rates in `.orchestrator/rates.json`: not "
           "what a subscription (Claude Pro or Max, ChatGPT Plus) costs you.", ""]
    out += _overhead(db)
    return "\n".join(out) + "\n"


def _runs_note(rows, empty_runs, groupable, agent_filtered, db, f):
    if agent_filtered:
        left = len(_runs_without_agents(db, f))
        return ("Runs without agent runs are left out by the agent, model, task or status filter (%d here)." % left
                if left else "")
    total = len({r["run_id"] for r in rows}) + len(empty_runs)
    if groupable or not empty_runs:
        return "Runs: %d, of which %d had no agent runs." % (total, len(empty_runs))
    return "Runs: %d, of which %d had no agent runs (not in the rows above)." % (total, len(empty_runs))


def _overhead(db):
    rows = db.execute("SELECT elapsed_ms, ok FROM ingest_log").fetchall()
    if not rows:
        return ["## Instrumentation overhead", "", "No hook calls recorded."]
    ms = [r[0] for r in rows if r[0] is not None]
    return ["## Instrumentation overhead", "",
            "Hook calls %d · errors %d · in-process median %.1f ms · p95 %.1f ms (starting bash and Python adds to "
            "each call)" % (len(rows), sum(1 for r in rows if not r[1]), statistics.median(ms), _p95(ms))]


def report(db, run, rates_path):
    """One run as Markdown, or None when there is no such run. run: a run id or "last"."""
    q = "SELECT run_id, status, total_duration_ms, runtime, project_id, started_at, finished_at, starts FROM runs "
    row = db.execute(q + ("ORDER BY started_at DESC LIMIT 1" if run == "last" else "WHERE run_id = ?"),
                     () if run == "last" else (run,)).fetchone()
    if row is None:
        return None
    run_id, status, ms, runtime, project, started, finished, starts = row
    rows = sorted((r for r in _load(db) if r["run_id"] == run_id), key=lambda r: r["started"])
    fin = [r for r in rows if r["finished"]]
    tok = _sum_tokens(rows)
    out = ["# Run %s" % run_id, "",
           "Status %s · wall time %s · runtime %s · project %s" % (status or NA, _secs(ms), runtime or NA,
                                                                   project or NA),
           "Started %s · finished %s · starts %s" % (started or NA, finished or NA, starts or NA), "",
           "## Agent runs", "", "| Agent run | Agent | Task | Model | Status | Duration | Tokens (reported) |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        state = ("failed launch" if r["failed_launch"] else "in progress" if r["in_progress"] else
                 "unfinished" if r["unfinished"] else r["status"] or NA)
        out.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            r["short"], r["agent_type"] or NA, r["task_id"] or NA, r["model"] or NA, state, _secs(r["duration"]),
            _n(sum(r["tokens"].values())) if r["tokens"] else "not available"))
    out += ["", "Coverage %d/%d · tokens %s (agent runs with reported usage only)" % (
        sum(r["covered"] for r in fin), len(fin), _n(sum(tok.values())) if tok else NA)]
    rates, _, _ = api_cost.load_rates(rates_path)
    value, why = _cost(rows, rates)
    out += ["API-equivalent (estimated, combined cache-write rate): %s. Not what a subscription costs you." % (
        why if value is None else "%s %s" % (value[0], value[1].quantize(_CENT)))]
    crit, task_status = _criteria(db)
    tasks = sorted({r["task_id"] for r in rows if r["task_id"]})
    out += ["", "## Criteria of the tasks this run worked on (not attributed to the run)", ""]
    if tasks:
        out += ["| Task | Status | Criteria |", "|---|---|---|"]
        for tk in tasks:
            cs = " · ".join("%s %s" % c for c in crit.get(tk, [])) or "no criteria recorded"
            out.append("| %s | %s | %s |" % (tk, task_status.get(tk) or NA, cs))
    else:
        out.append("No task named in this run's briefs.")
    return "\n".join(out) + "\n"
