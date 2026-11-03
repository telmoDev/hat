"""Compare two sets of benchmark results (the JSON files `scripts/benchmark.py result` writes), as Markdown.
Read-only, no model calls. Called by `telemetry.py benchmark <dirA> <dirB>`.

Runs are compared only for the same task (same task hash: request, criteria, checks, fixture, grading code and
session settings), runtime and named models; a run without a named model, or with a blocked criterion, isn't.
Quality and consumption are shown apart, each as n, median and range. A quality regression is never read as an
efficiency gain (each mandatory criterion's pass rate is compared, not only their count); overlapping ranges show no
difference; tokens with incomplete coverage aren't compared; fewer
than 3 runs on a side is flagged. Wall time and cumulative agent time are different measures.
"""
import json
import os
import statistics

NA = "—"


def _load(d):
    out = []
    for name in sorted(os.listdir(d)):
        if name.endswith(".json"):
            with open(os.path.join(d, name), encoding="utf-8") as f:
                out.append(json.load(f))
    return out


def _fmt_n(v):
    return "{:,}".format(int(v)) if v == int(v) else "{:,.1f}".format(v)


def _spread(values, fmt):
    if not values:
        return NA
    mid, lo, hi = statistics.median(values), min(values), max(values)
    return fmt(mid) if lo == hi else "%s (%s–%s)" % (fmt(mid), fmt(lo), fmt(hi))


def _secs(ms):
    return "%.1f s" % (ms / 1000.0)


def _tel(r, key):
    return (r.get("telemetry") or {}).get(key)


def _all_tokens(r):
    """A run's tokens: main session plus agent runs when recorded (results since the main session is measured),
    else the agent runs' alone (older results)."""
    tel = r.get("telemetry") or {}
    return tel.get("total_tokens") if "total_tokens" in tel else tel.get("tokens")


def _tokens(runs):
    """Token totals of the runs, or None when any run lacks complete coverage."""
    totals = [(_all_tokens(r) or {}).get("total") for r in runs]
    return None if not runs or None in totals else totals


def _kind_row(task, side, runs):
    def med(get):
        vals = [get(r) for r in runs]
        return "incomplete" if None in vals or not vals else _fmt_n(statistics.median(vals))
    covs = {tuple(_tel(r, "coverage") or ()) for r in runs}
    cov = covs.pop() if len(covs) == 1 else ()
    return "| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
        task, side, med(lambda r: (_tel(r, "main_tokens") or {}).get("total")),
        med(lambda r: (_tel(r, "tokens") or {}).get("total")),
        med(lambda r: (_all_tokens(r) or {}).get("input")), med(lambda r: (_all_tokens(r) or {}).get("output")),
        med(lambda r: (_all_tokens(r) or {}).get("cache_read")),
        med(lambda r: (_all_tokens(r) or {}).get("cache_write")),
        "%d/%d" % cov if len(cov) == 2 else "mixed")


def _rate(runs, code):
    """How often a criterion passed over the runs."""
    return sum((r.get("criteria") or {}).get(code) == "passed" for r in runs) / float(len(runs))


def _comparable(a, b):
    runs = a + b
    for key, label in (("task_hash", "task hash"), ("runtime", "runtime")):
        if len({r.get(key) for r in runs}) > 1:
            return label + " differs"
    mains = {(r.get("models") or {}).get("main") for r in runs}
    if mains & {None, "", "unavailable", "default"}:
        return "main model unknown in some runs: a run without a named model is never compared"
    if len(mains) > 1:
        return "main model differs"
    blocked = sorted({c for r in runs for c, s in (r.get("criteria") or {}).items() if s == "blocked"})
    if blocked:
        return "criteria blocked (%s): the check couldn't run" % ", ".join(blocked)
    if len({tuple((r.get("models") or {}).get("agents") or []) for r in runs}) > 1:
        return "agent models differ"
    return None


def _side(runs):
    labels = sorted({"%s · %s" % (r.get("label"), r.get("flow")) for r in runs})
    return ", ".join(labels) or NA


def compare(dir_a, dir_b):
    a_all, b_all = _load(dir_a), _load(dir_b)
    tasks = sorted({r["task"] for r in a_all} | {r["task"] for r in b_all})
    quality, consumption, reading, kinds = [], [], [], []
    for task in tasks:
        a = [r for r in a_all if r["task"] == task]
        b = [r for r in b_all if r["task"] == task]
        if not a or not b:
            reading.append("- %s: runs on one side only: no reading." % task)
            continue
        why = _comparable(a, b)
        qa, qb = [r["criteria_passed"] for r in a], [r["criteria_passed"] for r in b]
        total = a[0]["criteria_total"]
        fa = [(r.get("tests") or {}).get("failed") for r in a if r.get("tests")]
        fb = [(r.get("tests") or {}).get("failed") for r in b if r.get("tests")]
        quality.append("| %s | %d | %d | %s/%d | %s/%d | %s | %s |" % (
            task, len(a), len(b), _fmt_n(statistics.median(qa)), total, _fmt_n(statistics.median(qb)), total,
            _spread(fa, _fmt_n), _spread(fb, _fmt_n)))
        ta, tb = _tokens(a), _tokens(b)
        wa = [_tel(r, "wall_ms") for r in a if _tel(r, "wall_ms") is not None]
        wb = [_tel(r, "wall_ms") for r in b if _tel(r, "wall_ms") is not None]
        ca = [_tel(r, "agent_ms_cumulative") for r in a if _tel(r, "agent_ms_cumulative") is not None]
        cb = [_tel(r, "agent_ms_cumulative") for r in b if _tel(r, "agent_ms_cumulative") is not None]
        consumption.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            task, _spread(ta, _fmt_n) if ta else "incomplete", _spread(tb, _fmt_n) if tb else "incomplete",
            _spread(wa, _secs), _spread(wb, _secs), _spread(ca, _secs), _spread(cb, _secs)))
        kinds += [_kind_row(task, "A", a), _kind_row(task, "B", b)]
        if why:
            reading.append("- %s: not comparable (%s): no reading." % (task, why))
            continue
        if min(len(a), len(b)) < 3:
            reading.append("- %s: fewer than 3 runs on a side (%d vs %d): differences may be noise."
                           % (task, len(a), len(b)))
        ma, mb = statistics.median(qa), statistics.median(qb)
        worse = [c for c in sorted({c for r in a + b for c in (r.get("criteria") or {})})
                 if _rate(b, c) < _rate(a, c)]
        worse_tests = fa and fb and statistics.median(fb) > statistics.median(fa)
        if worse or mb < ma or worse_tests:
            what = (["criteria passed less often: " + ", ".join(worse)] if worse else []) + (
                ["more failing tests"] if worse_tests else []) or ["criteria passed median %s vs %s" % (
                    _fmt_n(mb), _fmt_n(ma))]
            reading.append("- %s: Quality regressed in B (%s): consumption differences are not an improvement."
                           % (task, "; ".join(what)))
            continue
        if mb > ma:
            reading.append("- %s: Quality improved in B (criteria passed median %s vs %s of %d)."
                           % (task, _fmt_n(mb), _fmt_n(ma), total))
        if ta is None or tb is None:
            reading.append("- %s: tokens incomplete on a side: no consumption reading." % task)
        elif max(tb) < min(ta):
            reading.append("- %s: B used fewer tokens than A in every run (n=%d vs %d), with quality not lower."
                           % (task, len(a), len(b)))
        elif max(ta) < min(tb):
            reading.append("- %s: B used more tokens than A in every run (n=%d vs %d)." % (task, len(a), len(b)))
        else:
            reading.append("- %s: token ranges overlap: no difference shown." % task)
    out = ["# Benchmark", "", "A: %s" % _side(a_all), "B: %s" % _side(b_all), "",
           "## Quality", "",
           "| Task | Runs A | Runs B | Criteria passed A (median) | Criteria passed B (median) | Failing tests A | "
           "Failing tests B |", "|---|---|---|---|---|---|---|"] + quality + [
           "", "## Consumption", "",
           "| Task | Tokens A | Tokens B | Wall time A | Wall time B | Agent time A (cumulative) | "
           "Agent time B (cumulative) |", "|---|---|---|---|---|---|---|"] + consumption + [
           "", "> Median (min–max) over the runs. Tokens as Claude Code reported them (main session plus agent runs), "
           "compared only with complete coverage. Wall time is the session's; cumulative agent time adds up agents "
           "that ran in parallel. Files consulted: unavailable.", "",
           "## Tokens by kind (median)", "",
           "| Task | Side | Main session | Agent runs | Input | Output | Cache read | Cache write | Agent coverage |",
           "|---|---|---|---|---|---|---|---|---|"] + kinds + [
           "", "> Answering without delegating can be the right call: fewer agent tokens isn't better by itself.", "",
           "## Reading", ""] + (reading or ["- no tasks"]) + [
           "", "> A quality regression is never read as an efficiency gain, and overlapping ranges show no difference."]
    return "\n".join(out) + "\n"
