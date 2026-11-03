#!/usr/bin/env python3
"""The benchmark harness: fixed tasks on a fixed fixture, run on demand, checked without any model.
  python3 scripts/benchmark.py prepare <B1..B5> <current|v0.7.0> <dir>   a fresh workspace for one task and flow
  python3 scripts/benchmark.py run <dir> --model <m>                     the one step that calls a model: a
                                                                         `claude -p` session with the task's request
  python3 scripts/benchmark.py check <dir>                               the task's criteria, as JSON
  python3 scripts/benchmark.py result <dir> --label <l> [--out <dir>]    criteria + telemetry -> one result JSON
Compare two sets of results with `python3 .orchestrator/scripts/telemetry.py benchmark <dirA> <dirB>`.

Both flows get the same measurement layer (the current telemetry), so what differs is only the flow under test.
The checks run on a copy of the workspace, with acceptance tests the session never saw (benchmark/checks/).
A result holds ids, versions, statuses and figures: never a prompt, an answer, code, a path or a transcript.
Files consulted are recorded as unavailable: no hook reports them.
"""
import datetime
import hashlib
import inspect
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(REPO, "benchmark")
TASKS = ("B1", "B2", "B3", "B4", "B5")
FLOWS = ("current", "v0.7.0")
_LAYER_SRC = {
    ".orchestrator/scripts/telemetry.py": "orchestrator/scripts/telemetry.py",
    ".orchestrator/scripts/claude_transcript.py": "orchestrator/scripts/claude_transcript.py",
    ".orchestrator/scripts/odd_tasks.py": "orchestrator/scripts/odd_tasks.py",
    ".orchestrator/scripts/reports.py": "orchestrator/scripts/reports.py",
    ".orchestrator/scripts/api_cost.py": "orchestrator/scripts/api_cost.py",
    ".orchestrator/scripts/benchmark_report.py": "orchestrator/scripts/benchmark_report.py",
    ".orchestrator/hooks/telemetry.sh": "orchestrator/hooks/telemetry.sh",
}
MEASUREMENT_LAYER = sorted(_LAYER_SRC)
SUFFIX = ("\n\nWork in this workspace. Don't push or open pull requests: finish with local commits. When nothing is "
          "left to do, stop.")


def _run(cmd, cwd=None, env=None, timeout=300):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, encoding="utf-8", errors="replace",
                          timeout=timeout)


def _files(root):
    """Relative paths under root, sorted, without .git and __pycache__."""
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in (".git", "__pycache__"))
        out += [os.path.relpath(os.path.join(d, f), root).replace("\\", "/") for f in sorted(files)]
    return sorted(out)


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read().replace(b"\r\n", b"\n")


# The code that decides each task's criteria; part of its hash, with the session's settings.
CHECK_CODE = {"B1": ("_check_b1", "_fixture_totals"), "B2": ("_hidden_py", "_unittest", "_by_criterion", "_py_key"),
              "B3": ("_hidden_py", "_unittest", "_by_criterion", "_py_key"),
              "B4": ("_check_b4", "_node_tests", "_by_criterion", "_js_key"), "B5": ("_check_b5", "_probe", "_unittest")}


def task_hash(task, base=BENCH):
    """What makes two runs of a task the same task: its file (request and criteria), its hidden checks, the
    fixture, the harness code that grades it, and the session's settings (the request's suffix, the command)."""
    h = hashlib.sha256()
    parts = ["tasks/%s.md" % task] + ["checks/" + n for n in sorted(os.listdir(os.path.join(base, "checks")))
                                      if n.startswith(task.lower() + "_")]
    parts += ["fixture/" + f for f in _files(os.path.join(base, "fixture"))]
    for rel in parts:
        h.update(rel.encode() + b"\0" + _read_bytes(os.path.join(base, rel)) + b"\0")
    me = sys.modules[__name__]
    for name in CHECK_CODE[task]:
        h.update(name.encode() + b"\0" + inspect.getsource(getattr(me, name)).replace("\r\n", "\n").encode() + b"\0")
    h.update(repr(sorted(B1_FUNCTIONS) if task == "B1" else []).encode())
    h.update(SUFFIX.encode() + repr(run_command(None, "<model>")).encode())
    return h.hexdigest()[:16]


def request(task):
    with open(os.path.join(BENCH, "tasks", task + ".md"), encoding="utf-8") as f:
        body = f.read()
    return re.search(r"^## Request\n(.*?)(?=^## |\Z)", body, re.S | re.M).group(1).strip()


# prepare --------------------------------------------------------------------------------------------------------

def prepare(task, flow, dest, env=None):
    if task not in TASKS or flow not in FLOWS:
        raise ValueError("task is one of %s, flow one of %s" % (", ".join(TASKS), ", ".join(FLOWS)))
    if os.path.exists(dest) and os.listdir(dest):
        raise ValueError("%s is not empty" % dest)
    env = env or os.environ.copy()
    for repo in ("api", "web"):
        shutil.copytree(os.path.join(BENCH, "fixture", repo), os.path.join(dest, repo),
                        ignore=shutil.ignore_patterns("__pycache__"))
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-qm", "chore: fixture"]):
            r = _run(cmd, cwd=os.path.join(dest, repo), env=env)
            if r.returncode:
                raise RuntimeError("%s: %s" % (" ".join(cmd), r.stderr.strip()))
    skill, tmp = REPO, None
    if flow != "current":
        tmp = tempfile.mkdtemp()
        archive = subprocess.run(["git", "archive", flow], cwd=REPO, capture_output=True, check=True).stdout
        tarfile.open(fileobj=io.BytesIO(archive)).extractall(tmp)
        skill = tmp
    try:
        r = _run([shutil.which("bash") or "bash", os.path.join(skill, "scripts", "scaffold.sh"), "--git", "--tools",
                  "claude", dest.replace("\\", "/")], env=env)
        if r.returncode:
            raise RuntimeError("scaffold: " + (r.stderr or r.stdout).strip())
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    _install_measurement(dest)
    meta = {"task": task, "flow": flow, "task_hash": task_hash(task),
            "skill_commit": _run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO).stdout.strip()}
    os.makedirs(os.path.join(dest, ".bench"), exist_ok=True)
    with open(os.path.join(dest, ".bench", "task.json"), "w") as f:
        json.dump(meta, f, indent=2)
    for cmd in (["git", "add", "-A"], ["git", "commit", "-qm", "chore: benchmark workspace"]):
        r = _run(cmd, cwd=dest, env=env)
        if r.returncode:
            raise RuntimeError("%s: %s" % (" ".join(cmd), r.stderr.strip()))
    return meta


def _install_measurement(dest):
    """The current telemetry, the same bytes in both flows, wired into .claude/settings.json."""
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import update  # add_telemetry_hooks
    for rel, src in _LAYER_SRC.items():
        path = os.path.join(dest, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.copy(os.path.join(REPO, "templates", *src.split("/")), path)
    settings_path = os.path.join(dest, ".claude", "settings.json")
    with open(settings_path, encoding="utf-8") as f:
        settings = json.load(f)
    with open(os.path.join(REPO, "templates", "claude", "settings.json"), encoding="utf-8") as f:
        update.add_telemetry_hooks(settings, json.load(f))
    with open(settings_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(settings, indent=2) + "\n")
    conf = os.path.join(dest, ".orchestrator", "orchestrator.conf")
    with open(conf, encoding="utf-8") as f:
        text = f.read()
    for key in ("TELEMETRY", "TELEMETRY_TRANSCRIPTS"):
        if not re.search(r"^%s=" % key, text, re.M):
            text += '%s="on"\n' % key
    with open(conf, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    gi = os.path.join(dest, ".gitignore")
    with open(gi, encoding="utf-8") as f:
        lines = f.read().splitlines()
    with open(gi, "a", encoding="utf-8", newline="\n") as f:
        for line in (".orchestrator/telemetry/", "/.bench/answer.md", "/.bench/run.json"):
            if line not in lines:
                f.write(line + "\n")


# run (the only model step) ---------------------------------------------------------------------------------------

def run_command(ws, model=None):
    """The `claude -p` session for the workspace's task; the request goes on stdin."""
    cmd = ["claude", "-p", "--permission-mode", "acceptEdits", "--allowedTools",
           "Bash(python3:*) Bash(python:*) Bash(node:*) Bash(git:*)"]
    return cmd + (["--model", model] if model else [])


def run(ws, model):
    """The one model step. The model is required: a run is compared only with runs of the same, named model."""
    if os.environ.get("ORCH_BENCH_NO_MODEL"):
        raise SystemExit("benchmark: run refused: ORCH_BENCH_NO_MODEL is set (tests never start a model session)")
    if not model:
        raise SystemExit("benchmark: run needs --model <model>")
    with open(os.path.join(ws, ".bench", "task.json")) as f:
        meta = json.load(f)
    cmd = run_command(ws, model)
    version = _run([cmd[0], "--version"]).stdout.strip() or "unavailable"
    with open(os.path.join(ws, ".bench", "run.json"), "w") as f:
        json.dump({"main_model": model, "claude_code_version": version}, f, indent=2)
    p = subprocess.run(cmd, cwd=ws, input=request(meta["task"]) + SUFFIX, capture_output=True, encoding="utf-8",
                       errors="replace", timeout=3600)
    with open(os.path.join(ws, ".bench", "answer.md"), "w", encoding="utf-8") as f:
        f.write(p.stdout)
    return p.returncode


# checks ---------------------------------------------------------------------------------------------------------

def _copy(ws, repo):
    tmp = tempfile.mkdtemp()
    dest = os.path.join(tmp, repo)
    shutil.copytree(os.path.join(ws, repo), dest, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    return tmp, dest


_PY_LINE = re.compile(r"^(test_\w+) \(.*\) \.\.\. (ok|FAIL|ERROR|skipped.*|expected failure)$", re.M)


def _unittest(cwd, target=None):
    """(per-test status, passed, failed) of the repo's tests, or of one module."""
    cmd = [sys.executable, "-m", "unittest"] + (["-v", target] if target else ["discover", "-v", "-s", "tests", "-t", "."])
    r = _run(cmd, cwd=cwd)
    out = r.stderr + r.stdout
    tests = {m.group(1): m.group(2) for m in _PY_LINE.finditer(out)}
    ran = re.search(r"^Ran (\d+) tests?", out, re.M)
    bad = re.search(r"^FAILED \((.*)\)", out, re.M)
    failed = sum(int(n) for n in re.findall(r"(?:failures|errors)=(\d+)", bad.group(1))) if bad else 0
    total = int(ran.group(1)) if ran else 0
    return tests, total - failed, failed if ran else max(failed, 1)


def _node():
    node = os.environ.get("ORCH_BENCH_NODE") or shutil.which("node")
    return node if node and os.path.isfile(node) else None


_TAP = re.compile(r"^(not )?ok \d+ - (.+?)(?: #.*)?$", re.M)


def _node_tests(cwd, files=()):
    """(per-test status, passed, failed) from `node --test`, or None without Node."""
    node = _node()
    if not node:
        return None
    r = _run([node, "--test", "--test-reporter=tap"] + list(files), cwd=cwd)
    if "bad option" in r.stderr:
        r = _run([node, "--test"] + list(files), cwd=cwd)
    tests = {m.group(2).strip(): "FAIL" if m.group(1) else "ok" for m in _TAP.finditer(r.stdout)}
    passed = re.search(r"^# pass (\d+)", r.stdout, re.M)
    failed = re.search(r"^# fail (\d+)", r.stdout, re.M)
    return tests, int(passed.group(1)) if passed else 0, int(failed.group(1)) if failed else (1 if r.returncode else 0)


def _by_criterion(tests, codes, key):
    """A criterion passes when it has tests and they all pass."""
    out = {}
    for code in codes:
        mine = [s for name, s in tests.items() if key(name) == code]
        out[code] = "passed" if mine and all(s == "ok" for s in mine) else "failed"
    return out


def _py_key(name):
    m = re.match(r"test_(O\d+)_", name)
    return m.group(1) if m else None


def _js_key(name):
    m = re.match(r"(O\d+) ", name)
    return m.group(1) if m else None


def _hidden_py(ws, task, codes):
    tmp, api = _copy(ws, "api")
    try:
        _, passed, failed = _unittest(api)
        shutil.copy(os.path.join(BENCH, "checks", "%s_hidden_test.py" % task.lower()),
                    os.path.join(api, "tests", "test_bench_hidden.py"))
        tests, _, _ = _unittest(api, "tests.test_bench_hidden")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    crit = _by_criterion(tests, codes, _py_key)
    crit["O%d" % (len(codes) + 1)] = "passed" if failed == 0 and passed > 0 else "failed"
    return {"criteria": crit, "tests": {"passed": passed, "failed": failed}}


def _fixture_totals():
    """What the untouched fixture computes for B1's carts (and how often the coupon comes off cart B)."""
    code = ("import json; from shop.cart import Cart\n"
            "def c(*i):\n x = Cart()\n for p, q in i: x.add(p, q)\n return x\n"
            "b = c((3, 1))\n"
            "print(json.dumps({'A': c((1, 2)).total(), 'B': b.total('SAVE5'), 'C': c((1, 10)).total('SAVE5'),"
            " 'times': (b.subtotal() - b.total('SAVE5')) // 500}))")
    r = _run([sys.executable, "-c", code], cwd=os.path.join(BENCH, "fixture", "api"))
    return json.loads(r.stdout)


B1_FUNCTIONS = {"cart.Cart.total", "cart.Cart.subtotal", "pricing.apply_discounts", "pricing.bulk_discount",
                "pricing.coupon_discount"}


def _check_b1(ws):
    answer = None
    try:
        with open(os.path.join(ws, ".bench", "answer.md"), encoding="utf-8") as f:
            blocks = re.findall(r"```json\s*\n(.*?)```", f.read(), re.S)
        answer = json.loads(blocks[-1]) if blocks else None
    except (OSError, ValueError):
        answer = None
    if not isinstance(answer, dict):
        answer = {}
    names = {re.sub(r"^shop\.|\(\)$", "", str(n).strip()) for n in answer.get("functions") or []}
    expected = _fixture_totals()
    totals = answer.get("totals") if isinstance(answer.get("totals"), dict) else {}
    unchanged = all(_files(os.path.join(ws, r)) == _files(os.path.join(BENCH, "fixture", r)) and all(
        _read_bytes(os.path.join(ws, r, f)) == _read_bytes(os.path.join(BENCH, "fixture", r, f))
        for f in _files(os.path.join(ws, r))) for r in ("api", "web"))
    return {"criteria": {
        "O1": "passed" if names == B1_FUNCTIONS else "failed",
        "O2": "passed" if all(totals.get(k) == expected[k] for k in "ABC") else "failed",
        "O3": "passed" if answer.get("coupon_applied_times") == expected["times"] else "failed",
        "O4": "passed" if unchanged else "failed"}, "tests": None}


def _check_b4(ws):
    with open(os.path.join(ws, "web", "index.html"), encoding="utf-8") as f:
        header = re.search(r"<header[^>]*>(.*?)</header>", f.read(), re.S)
    o3 = "passed" if header and re.search(r"""id=["']cart-badge["']""", header.group(1)) else "failed"
    tmp, web = _copy(ws, "web")
    try:
        repo = _node_tests(web)
        if repo is None:
            return {"criteria": {"O1": "blocked", "O2": "blocked", "O3": o3, "O4": "blocked"}, "tests": None,
                    "note": "Node not found"}
        shutil.copy(os.path.join(BENCH, "checks", "b4_hidden.test.mjs"), os.path.join(web, "tests", "zz-bench-hidden.mjs"))
        hidden = _node_tests(web, [os.path.join("tests", "zz-bench-hidden.mjs")])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    crit = _by_criterion(hidden[0], ("O1", "O2"), _js_key)
    crit["O3"] = o3
    crit["O4"] = "passed" if repo[2] == 0 and repo[1] > 0 else "failed"
    return {"criteria": crit, "tests": {"passed": repo[1], "failed": repo[2]}}


def _probe(api_dir):
    shutil.copy(os.path.join(BENCH, "checks", "b5_probe.py"), os.path.join(api_dir, "bench_probe.py"))
    r = _run([sys.executable, "bench_probe.py"], cwd=api_dir)
    return r.stdout if r.returncode == 0 else None


def _check_b5(ws):
    lines = 0
    for rel in _files(os.path.join(ws, "api")):
        if rel.endswith(".py") and not rel.startswith("tests/"):
            with open(os.path.join(ws, "api", rel), encoding="utf-8") as f:
                lines += sum("02d" in line for line in f)
    tmp, api = _copy(ws, "api")
    ref_tmp = tempfile.mkdtemp()
    try:
        ref = os.path.join(ref_tmp, "api")
        shutil.copytree(os.path.join(BENCH, "fixture", "api"), ref, ignore=shutil.ignore_patterns("__pycache__"))
        before, after = _probe(ref), _probe(api)
        os.remove(os.path.join(api, "bench_probe.py"))
        _, passed, failed = _unittest(api)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(ref_tmp, ignore_errors=True)
    return {"criteria": {"O1": "passed" if lines == 1 else "failed",
                         "O2": "passed" if before is not None and after == before else "failed",
                         "O3": "passed" if failed == 0 and passed > 0 else "failed"},
            "tests": {"passed": passed, "failed": failed}}


def check(task, ws):
    if task == "B1":
        return _check_b1(ws)
    if task in ("B2", "B3"):
        return _hidden_py(ws, task, ("O1", "O2", "O3"))
    if task == "B4":
        return _check_b4(ws)
    if task == "B5":
        return _check_b5(ws)
    raise ValueError("unknown task " + task)


# result ---------------------------------------------------------------------------------------------------------

def _telemetry(ws):
    path = os.path.join(ws, ".orchestrator", "telemetry", "telemetry.db")
    if not os.path.exists(path):
        return None
    db = sqlite3.connect(path)
    try:
        runs = db.execute("SELECT total_duration_ms FROM runs").fetchall()
        rows = db.execute("SELECT i.invocation_id, i.agent_id, i.agent_type, i.model, i.runtime, i.status, "
                          "i.duration_ms, i.retry_number, p.status FROM agent_invocations i "
                          "LEFT JOIN agent_invocations p ON p.invocation_id = i.parent_invocation_id").fetchall()
        usage = {}
        for inv, *tok in db.execute("SELECT invocation_id, input_tokens, output_tokens, cache_read_tokens, "
                                    "cache_write_tokens FROM usage_records WHERE source = 'runtime_reported'"):
            u = usage.setdefault(inv, [0, 0, 0, 0])
            for i, v in enumerate(tok):
                u[i] += v or 0
    finally:
        db.close()
    deleg = [r for r in rows if r[1] is not None]
    finished = [r for r in deleg if r[5] in ("completed", "success", "failed")]
    covered = [r for r in finished if r[0] in usage]
    agents = {}
    for r in deleg:
        agents[r[2] or "unknown"] = agents.get(r[2] or "unknown", 0) + 1
    tokens = None
    if finished and len(covered) == len(finished) and all(r[4] == "claude-code" for r in covered):
        t = [sum(usage[r[0]][i] for r in covered) for i in range(4)]
        tokens = {"input": t[0], "output": t[1], "cache_read": t[2], "cache_write": t[3], "total": sum(t)}
    walls = [r[0] for r in runs]
    return {"runs": len(runs), "wall_ms": sum(walls) if walls and None not in walls else None,
            "agent_ms_cumulative": sum(r[6] or 0 for r in finished) if finished else None,
            "delegations": len(deleg), "agents": agents,
            "retries": sum(1 for r in deleg if (r[7] or 0) > 0 and r[8] == "failed"),
            "reinvocations": sum(1 for r in deleg if (r[7] or 0) > 0),
            "coverage": [len(covered), len(finished)], "tokens": tokens,
            "agent_models": sorted({r[3] for r in deleg if r[3]})}


def write_result(ws, label, out_dir):
    with open(os.path.join(ws, ".bench", "task.json")) as f:
        meta = json.load(f)
    run_meta = {}
    if os.path.exists(os.path.join(ws, ".bench", "run.json")):
        with open(os.path.join(ws, ".bench", "run.json")) as f:
            run_meta = json.load(f)
    c = check(meta["task"], ws)
    tel = _telemetry(ws)
    crit = c["criteria"]
    result = {
        "schema": 1, "label": label, "date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
        "task": meta["task"], "task_hash": meta["task_hash"], "flow": meta["flow"],
        "skill_commit": meta["skill_commit"], "runtime": "claude-code",
        "claude_code_version": run_meta.get("claude_code_version", "unavailable"),
        "models": {"main": run_meta.get("main_model", "unavailable"),
                   "agents": tel.pop("agent_models") if tel else []},
        "criteria": crit, "criteria_passed": sum(s == "passed" for s in crit.values()), "criteria_total": len(crit),
        "tests": c["tests"], "telemetry": tel, "files_consulted": "unavailable"}
    os.makedirs(out_dir, exist_ok=True)
    n = 1
    while os.path.exists(os.path.join(out_dir, "%s-%s-%d.json" % (meta["task"], meta["flow"], n))):
        n += 1
    path = os.path.join(out_dir, "%s-%s-%d.json" % (meta["task"], meta["flow"], n))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return path


def main(argv):
    args = argv[1:]
    if args[:1] == ["prepare"] and len(args) == 4:
        print(json.dumps(prepare(args[1], args[2], os.path.abspath(args[3])), indent=2))
        return 0
    if args[:1] == ["run"]:
        if len(args) != 4 or args[2] != "--model":
            print("benchmark: run needs --model <model>: runs compare only with the same, named model",
                  file=sys.stderr)
            return 2
        try:
            return run(os.path.abspath(args[1]), args[3])
        except SystemExit as err:
            print(err, file=sys.stderr)
            return 3
    if args[:1] == ["check"] and len(args) == 2:
        with open(os.path.join(args[1], ".bench", "task.json")) as f:
            task = json.load(f)["task"]
        print(json.dumps(check(task, os.path.abspath(args[1])), indent=2))
        return 0
    if args[:1] == ["result"] and "--label" in args:
        label = args[args.index("--label") + 1]
        out = args[args.index("--out") + 1] if "--out" in args else os.path.join(BENCH, "results", label)
        print(write_result(os.path.abspath(args[1]), label, out))
        return 0
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
