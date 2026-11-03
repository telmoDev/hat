"""Tests for T10: the benchmark fixture, its checks, the harness (scripts/benchmark.py) and the comparison
(`telemetry.py benchmark`, benchmark_report.py). No model is ever called: sessions are replaced by the reference
solutions in benchmark/solutions/ and by recorded telemetry events.
  python3 -m unittest discover -s tests
Needs git and bash; the web checks need Node 18+ and are skipped without it.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BENCH = os.path.join(REPO, "benchmark")
# No test may start a model session: `run` refuses while this is set, in this process and every subprocess.
os.environ["ORCH_BENCH_NO_MODEL"] = "1"
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.path.insert(0, os.path.join(REPO, "templates", "orchestrator", "scripts"))
import benchmark as bm  # noqa: E402
import benchmark_report as br  # noqa: E402
import telemetry as t  # noqa: E402

NODE = shutil.which("node")
GITCFG = None


def git_env():
    global GITCFG
    if GITCFG is None:
        GITCFG = os.path.join(tempfile.mkdtemp(), "gitconfig")
        with open(GITCFG, "w") as f:
            f.write("[user]\n\tname = t\n\temail = t@example.com\n[init]\n\tdefaultBranch = main\n"
                    "[commit]\n\tgpgsign = false\n[core]\n\tautocrlf = false\n")
    return dict(os.environ, GIT_CONFIG_GLOBAL=GITCFG, GIT_CONFIG_NOSYSTEM="1")


def copy_fixture(dest):
    for repo in ("api", "web"):
        shutil.copytree(os.path.join(BENCH, "fixture", repo), os.path.join(dest, repo))
    os.makedirs(os.path.join(dest, ".bench"))
    return dest


def apply_solution(task, ws):
    src = os.path.join(BENCH, "solutions", task)
    for d, _, files in os.walk(src):
        for name in files:
            rel = os.path.relpath(os.path.join(d, name), src)
            dest = os.path.join(ws, ".bench", "answer.md") if rel == "answer.md" else os.path.join(ws, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy(os.path.join(d, name), dest)


class Fixture(unittest.TestCase):
    def test_api_tests_pass(self):
        p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                           cwd=os.path.join(BENCH, "fixture", "api"), capture_output=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)

    @unittest.skipUnless(NODE, "Node not installed")
    def test_web_tests_pass(self):
        p = subprocess.run([NODE, "--test"], cwd=os.path.join(BENCH, "fixture", "web"), capture_output=True,
                           timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout)


class Checks(unittest.TestCase):
    """Each task: the untouched fixture fails its main criteria; the reference solution passes them all."""

    def setUp(self):
        self.ws = copy_fixture(os.path.join(tempfile.mkdtemp(), "ws"))
        self.addCleanup(shutil.rmtree, os.path.dirname(self.ws), True)

    def statuses(self, task):
        return bm.check(task, self.ws)["criteria"]

    def test_b1(self):
        self.assertEqual(self.statuses("B1"), {"O1": "failed", "O2": "failed", "O3": "failed", "O4": "passed"})
        apply_solution("B1", self.ws)
        self.assertEqual(set(self.statuses("B1").values()), {"passed"})

    def test_b1_is_semantic(self):
        apply_solution("B1", self.ws)
        path = os.path.join(self.ws, ".bench", "answer.md")
        with open(path) as f:
            right = f.read()
        with open(path, "w") as f:
            f.write(right.replace('"B": 1500', '"B": 2000').replace('"coupon_applied_times": 2',
                                                                     '"coupon_applied_times": 1'))
        self.assertEqual(self.statuses("B1"), {"O1": "passed", "O2": "failed", "O3": "failed", "O4": "passed"})
        with open(path, "w") as f:  # a function the total never calls
            f.write(right.replace('"pricing.bulk_discount",', '"pricing.bulk_discount", "catalog.all_products",'))
        self.assertEqual(self.statuses("B1")["O1"], "failed")
        with open(path, "w") as f:  # one it calls left out
            f.write(right.replace('"catalog.get", ', ''))
        self.assertEqual(self.statuses("B1")["O1"], "failed")
        with open(os.path.join(self.ws, "api", "shop", "pricing.py"), "a") as f:
            f.write("\n# touched\n")
        with open(path, "w") as f:
            f.write(right)
        self.assertEqual(self.statuses("B1")["O4"], "failed")

    def test_b2(self):
        self.assertEqual(self.statuses("B2")["O1"], "failed")
        apply_solution("B2", self.ws)
        result = bm.check("B2", self.ws)
        self.assertEqual(set(result["criteria"].values()), {"passed"})
        self.assertEqual(result["tests"]["failed"], 0)
        self.assertGreater(result["tests"]["passed"], 0)

    def test_b3(self):
        s = self.statuses("B3")
        self.assertEqual((s["O1"], s["O2"]), ("failed", "failed"))
        apply_solution("B3", self.ws)
        self.assertEqual(set(self.statuses("B3").values()), {"passed"})

    @unittest.skipUnless(NODE, "Node not installed")
    def test_b4(self):
        self.assertEqual(self.statuses("B4"), {"O1": "failed", "O2": "failed", "O3": "failed", "O4": "passed"})
        apply_solution("B4", self.ws)
        self.assertEqual(set(self.statuses("B4").values()), {"passed"})

    def test_b4_without_node_is_blocked_not_failed(self):
        apply_solution("B4", self.ws)
        old = os.environ.get("ORCH_BENCH_NODE")
        os.environ["ORCH_BENCH_NODE"] = os.path.join(self.ws, "no-node-here")
        try:
            s = self.statuses("B4")
        finally:
            os.environ.pop("ORCH_BENCH_NODE") if old is None else os.environ.__setitem__("ORCH_BENCH_NODE", old)
        self.assertEqual((s["O1"], s["O2"], s["O3"], s["O4"]), ("blocked", "blocked", "passed", "blocked"))

    def test_b5(self):
        self.assertEqual(self.statuses("B5"), {"O1": "failed", "O2": "passed", "O3": "passed"})
        apply_solution("B5", self.ws)
        self.assertEqual(set(self.statuses("B5").values()), {"passed"})

    def test_b5_checks_behaviour_not_just_tests(self):
        apply_solution("B5", self.ws)
        path = os.path.join(self.ws, "api", "shop", "catalog.py")
        with open(path) as f:
            body = f.read()
        with open(path, "w") as f:  # a refactor that keeps the visible tests green but changes some outputs
            f.write(body.replace('return "$%d.%02d" % (cents // 100, cents % 100)',
                                 'return "$%d.%02d" % (cents // 100, cents % 100) if cents < 100000 else "$big"'))
        s = self.statuses("B5")
        self.assertEqual((s["O2"], s["O3"]), ("failed", "passed"))


class B1Functions(unittest.TestCase):
    def test_the_expected_functions_are_every_one_cart_total_calls(self):
        # Seen in the pilot: both flows also named Cart.quantity (the bulk discount's quantity) and catalog.get
        # (inside Cart.subtotal), and they were right.
        self.assertEqual(bm.B1_FUNCTIONS, {"cart.Cart.total", "cart.Cart.subtotal", "cart.Cart.quantity",
                                           "catalog.get", "pricing.apply_discounts", "pricing.bulk_discount",
                                           "pricing.coupon_discount"})


class Hash(unittest.TestCase):
    def test_the_hash_follows_the_request_the_checks_and_the_fixture(self):
        base = os.path.join(tempfile.mkdtemp(), "benchmark")
        self.addCleanup(shutil.rmtree, os.path.dirname(base), True)
        shutil.copytree(BENCH, base, ignore=shutil.ignore_patterns("__pycache__", "results"))
        h = bm.task_hash("B3", base)
        self.assertEqual(h, bm.task_hash("B3", BENCH))
        for rel in ("tasks/B3.md", "checks/b3_hidden_test.py", "fixture/api/shop/cart.py"):
            with open(os.path.join(base, rel), "a") as f:
                f.write("\n")
            self.assertNotEqual(bm.task_hash("B3", base), h, rel)
            h = bm.task_hash("B3", base)


class HashCoversTheChecksAndTheSession(unittest.TestCase):
    """Anything that changes the expected result or the session changes the hash, not only the task's files."""

    def test_check_code_and_run_settings(self):
        h = bm.task_hash("B1")
        saved = bm.B1_FUNCTIONS
        bm.B1_FUNCTIONS = saved | {"catalog.all_products"}
        try:
            self.assertNotEqual(bm.task_hash("B1"), h)
        finally:
            bm.B1_FUNCTIONS = saved
        saved_check = bm._check_b5
        h5 = bm.task_hash("B5")
        bm._check_b5 = lambda ws: {"criteria": {}, "tests": None}
        try:
            self.assertNotEqual(bm.task_hash("B5"), h5)
        finally:
            bm._check_b5 = saved_check
        h3 = bm.task_hash("B3")
        saved_suffix = bm.SUFFIX
        bm.SUFFIX = saved_suffix + " Be brief."
        try:
            self.assertNotEqual(bm.task_hash("B3"), h3)
        finally:
            bm.SUFFIX = saved_suffix
        self.assertEqual(bm.task_hash("B3"), h3)


class Prepare(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.ws = {}
        for flow in ("current", "v0.7.0"):
            cls.ws[flow] = os.path.join(cls.tmp, flow)
            bm.prepare("B3", flow, cls.ws[flow], env=git_env())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def read(self, flow, rel):
        with open(os.path.join(self.ws[flow], rel), "rb") as f:
            return f.read()

    def test_both_flows_get_the_same_measurement_layer(self):
        for rel in bm.MEASUREMENT_LAYER:
            self.assertEqual(self.read("current", rel), self.read("v0.7.0", rel), rel)
        for flow in self.ws:
            hooks = json.loads(self.read(flow, ".claude/settings.json"))["hooks"]
            for event in ("SessionStart", "SessionEnd", "SubagentStart", "SubagentStop", "PostToolUse",
                          "PostToolUseFailure"):
                n = sum("telemetry.sh" in h["command"] for g in hooks[event] for h in g["hooks"])
                self.assertEqual(n, 1, (flow, event))

    def test_the_flows_differ_where_they_should(self):
        self.assertNotEqual(self.read("current", "AGENTS.md"), self.read("v0.7.0", "AGENTS.md"))
        self.assertIn(b'TEMPLATE_VERSION="0.7.0"', self.read("v0.7.0", ".orchestrator/orchestrator.conf"))

    def test_meta_and_a_clean_start(self):
        for flow, ws in self.ws.items():
            meta = json.loads(self.read(flow, ".bench/task.json"))
            self.assertEqual((meta["task"], meta["flow"], meta["task_hash"]), ("B3", flow, bm.task_hash("B3")))
            for repo in ("api", "web", "."):
                out = subprocess.run(["git", "status", "--porcelain"], cwd=os.path.join(ws, repo),
                                     capture_output=True, text=True).stdout
                self.assertEqual(out.strip(), "", (flow, repo))
            self.assertFalse(os.path.exists(os.path.join(ws, ".bench", "answer.md")))

    def test_run_needs_a_model(self):
        p = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "benchmark.py"), "run", self.ws["current"]],
                           capture_output=True, timeout=60)
        self.assertEqual(p.returncode, 2)
        self.assertIn(b"--model", p.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.ws["current"], ".bench", "run.json")))

    def test_the_test_guard_stops_run_even_with_a_model(self):
        p = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "benchmark.py"), "run", self.ws["current"],
                            "--model", "haiku"], capture_output=True, timeout=60)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn(b"ORCH_BENCH_NO_MODEL", p.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.ws["current"], ".bench", "run.json")))

    def test_run_only_builds_its_command(self):
        cmd = bm.run_command(self.ws["current"], model="haiku")
        self.assertEqual(cmd[:2], ["claude", "-p"])
        self.assertIn("haiku", cmd)
        self.assertFalse(os.path.exists(os.path.join(self.ws["current"], ".bench", "run.json")))


class Result(unittest.TestCase):
    def test_result_json_is_complete_and_holds_no_content(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        ws = os.path.join(tmp, "ws")
        start = time.perf_counter()
        bm.prepare("B3", "current", ws, env=git_env())
        apply_solution("B3", ws)
        s = t.Store(os.path.join(ws, ".orchestrator", "telemetry", "telemetry.db"))

        def ev(kind, at, inv=None, task=None, key=None, **p):
            s.record(t.make_event(kind, "claude:s1", task_id=task, invocation_id=inv,
                                  timestamp="2026-11-04T10:%sZ" % at, key=key, payload=p))
        ev("run.started", "00:00", runtime="claude-code", project_id="ws")
        for aid, start_at, end_at, tokens in (("a1", "01:00", "03:00", 100), ("a2", "02:00", "04:00", 200)):
            ev("agent.started", start_at, "claude:" + aid, "fix#T1", agent_id=aid, agent_type="api-dev",
               model="claude-sonnet-5-5", runtime="claude-code")
            ev("agent.completed", end_at, "claude:" + aid)
            ev("usage.reported", end_at, "claude:" + aid, key="u", source="runtime_reported", model="claude-sonnet-5-5",
               input_tokens=tokens, output_tokens=10, cache_read_tokens=1000, cache_write_tokens=50)
        ev("agent.started", "00:00", "claude:s1:main", agent_type="main", runtime="claude-code", key="m0")
        ev("agent.completed", "10:00", "claude:s1:main", agent_type="main", runtime="claude-code", key="m1")
        ev("usage.reported", "10:00", "claude:s1:main", key="mu", source="runtime_reported", model="claude-haiku-5-5",
           input_tokens=9, output_tokens=90, cache_read_tokens=900, cache_write_tokens=9)
        ev("run.completed", "10:00", status="completed")
        s.close()
        path = bm.write_result(ws, "test-label", os.path.join(tmp, "results"))
        saved = bm.B1_FUNCTIONS
        bm.CHECK_CODE["B3"] = bm.CHECK_CODE["B3"] + ("_check_b1",)  # the grading code changed after prepare
        try:
            regraded = bm.write_result(ws, "test-label", os.path.join(tmp, "results"))
        finally:
            bm.CHECK_CODE["B3"] = bm.CHECK_CODE["B3"][:-1]
            bm.B1_FUNCTIONS = saved
        with open(regraded, encoding="utf-8") as f:
            again = json.load(f)
        self.assertNotEqual(again["task_hash"], again["regraded_from"])
        elapsed = time.perf_counter() - start
        with open(path, encoding="utf-8") as f:
            text = f.read()
        r = json.loads(text)
        self.assertEqual((r["task"], r["flow"], r["label"], r["runtime"]), ("B3", "current", "test-label", "claude-code"))
        self.assertEqual(r["task_hash"], bm.task_hash("B3"))
        self.assertNotIn("regraded_from", r)
        self.assertEqual((r["criteria_passed"], r["criteria_total"]), (4, 4))
        self.assertEqual(r["tests"]["failed"], 0)
        tel = r["telemetry"]
        self.assertEqual((tel["wall_ms"], tel["agent_ms_cumulative"]), (600000, 240000))  # kept apart
        self.assertEqual((tel["delegations"], tel["agents"], tel["coverage"]), (2, {"api-dev": 2}, [2, 2]))
        self.assertEqual(tel["tokens"], {"input": 300, "output": 20, "cache_read": 2000, "cache_write": 100,
                                         "total": 2420})
        self.assertEqual(tel["main_tokens"], {"input": 9, "output": 90, "cache_read": 900, "cache_write": 9,
                                              "total": 1008})
        self.assertEqual(tel["total_tokens"], {"input": 309, "output": 110, "cache_read": 2900, "cache_write": 109,
                                               "total": 3428})
        self.assertEqual(r["models"], {"main": "unavailable", "agents": ["claude-sonnet-5-5"]})
        self.assertEqual(r["files_consulted"], "unavailable")
        for secret in (tmp, os.path.expanduser("~"), "Cart totals are wrong", "def total", "SAVE5"):
            self.assertNotIn(secret, text)
        print("\nbenchmark T10 harness: prepare + check + result %.1f s" % elapsed)
        self.assertLess(elapsed, 10)


class NoDelegations(unittest.TestCase):
    def test_a_session_without_agents_has_zero_agent_tokens_and_its_main_tokens(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        os.makedirs(os.path.join(tmp, ".orchestrator", "telemetry"))
        s = t.Store(os.path.join(tmp, ".orchestrator", "telemetry", "telemetry.db"))
        for kind, p in (("agent.started", {"agent_type": "main", "runtime": "claude-code"}),
                        ("agent.completed", {"agent_type": "main", "runtime": "claude-code"}),
                        ("usage.reported", {"source": "runtime_reported", "model": "m", "input_tokens": 1,
                                            "output_tokens": 2, "cache_read_tokens": 3, "cache_write_tokens": 4})):
            s.record(t.make_event(kind, "claude:s1", invocation_id="claude:s1:main", key=kind, payload=p))
        s.close()
        tel = bm._telemetry(tmp)
        self.assertEqual((tel["delegations"], tel["coverage"]), (0, [0, 0]))
        self.assertEqual(tel["tokens"]["total"], 0)  # no agent ran: zero, not unknown
        self.assertEqual(tel["total_tokens"]["total"], 10)


def result(label, flow, tokens, passed=4, total=4, task="B3", task_hash="h3", main="m", agents=("a",),
           coverage=(2, 2), runtime="claude-code", criteria=None):
    criteria = criteria or {"O%d" % i: "passed" if i <= passed else "failed" for i in range(1, total + 1)}
    return {"schema": 1, "label": label, "task": task, "task_hash": task_hash, "flow": flow, "runtime": runtime,
            "models": {"main": main, "agents": list(agents)}, "criteria": criteria,
            "criteria_passed": sum(s == "passed" for s in criteria.values()), "criteria_total": total,
            "tests": {"passed": 5, "failed": 0},
            "telemetry": {"wall_ms": 60000, "agent_ms_cumulative": 90000, "delegations": 2, "retries": 0,
                          "reinvocations": 0, "coverage": list(coverage),
                          "tokens": None if coverage[0] < coverage[1] else {"total": tokens},
                          "main_tokens": {"total": 0}, "total_tokens": None if coverage[0] < coverage[1] else {
                              "input": 1, "output": 2, "cache_read": 3, "cache_write": tokens - 6, "total": tokens}},
            "files_consulted": "unavailable"}


class Compare(unittest.TestCase):
    def dirs(self, a, b):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        out = []
        for name, runs in (("A", a), ("B", b)):
            d = os.path.join(tmp, name)
            os.makedirs(d)
            for i, r in enumerate(runs):
                with open(os.path.join(d, "%s-%d.json" % (r["task"], i)), "w") as f:
                    json.dump(r, f)
            out.append(d)
        return out

    def test_quality_and_consumption_apart_with_n_median_and_range(self):
        a = [result("A", "v0.7.0", n) for n in (1000, 1100, 1200)]
        b = [result("B", "current", n) for n in (700, 800, 900)]
        out = br.compare(*self.dirs(a, b))
        self.assertIn("## Quality", out)
        self.assertIn("## Consumption", out)
        self.assertIn("| B3 | 3 | 3 | 4/4 | 4/4 |", out)
        self.assertIn("| B3 | 1,100 (1,000–1,200) | 800 (700–900) | 60.0 s | 60.0 s | 90.0 s | 90.0 s |", out)
        self.assertIn("B used fewer tokens than A in every run", out)

    def test_tokens_by_kind_main_and_agents_apart(self):
        out = br.compare(*self.dirs([result("A", "v0.7.0", n) for n in (1000, 1100, 1200)],
                                    [result("B", "current", n) for n in (700, 800, 900)]))
        self.assertIn("## Tokens by kind (median)", out)
        self.assertIn("| B3 | A | 0 | 1,100 | 1 | 2 | 3 | 1,094 | 2/2 |", out)
        self.assertIn("| B3 | B | 0 | 800 | 1 | 2 | 3 | 794 | 2/2 |", out)

    def test_a_quality_regression_is_never_an_efficiency_gain(self):
        a = [result("A", "v0.7.0", n) for n in (1000, 1100, 1200)]
        b = [result("B", "current", n, passed=3) for n in (700, 800, 900)]
        out = br.compare(*self.dirs(a, b))
        self.assertIn("Quality regressed in B", out)
        self.assertNotIn("fewer tokens", out)

    def test_every_mandatory_criterion_counts_not_just_the_count(self):
        swap_a = {"O1": "passed", "O2": "failed", "O3": "passed", "O4": "passed"}
        swap_b = {"O1": "failed", "O2": "passed", "O3": "passed", "O4": "passed"}  # same count, O1 got worse
        out = br.compare(*self.dirs([result("A", "x", n, criteria=swap_a) for n in (1000, 1100, 1200)],
                                    [result("B", "y", n, criteria=swap_b) for n in (700, 800, 900)]))
        self.assertIn("Quality regressed in B", out)
        self.assertIn("O1", out.split("Quality regressed in B")[1].splitlines()[0])
        self.assertNotIn("fewer tokens", out)

    def test_a_blocked_criterion_makes_runs_not_comparable(self):
        blocked = {"O1": "blocked", "O2": "blocked", "O3": "passed", "O4": "blocked"}
        out = br.compare(*self.dirs([result("A", "x", 1, task="B4")] * 3,
                                    [result("B", "y", 1, task="B4", criteria=blocked)] * 3))
        self.assertIn("not comparable", out)
        self.assertIn("blocked", out)

    def test_an_unknown_model_is_not_comparable(self):
        out = br.compare(*self.dirs([result("A", "x", 1, main="unavailable")] * 3,
                                    [result("B", "y", 1, main="unavailable")] * 3))
        self.assertIn("not comparable", out)
        self.assertIn("main model unknown", out)

    def test_overlapping_ranges_show_no_difference(self):
        out = br.compare(*self.dirs([result("A", "x", n) for n in (1000, 1300, 1500)],
                                    [result("B", "y", n) for n in (900, 1200, 1400)]))
        self.assertIn("ranges overlap", out)

    def test_not_comparable(self):
        for name, b in (("task hash", result("B", "y", 1, task_hash="other")),
                        ("models", result("B", "y", 1, agents=("other",))),
                        ("main model", result("B", "y", 1, main="other")),
                        ("runtime", result("B", "y", 1, runtime="codex"))):
            with self.subTest(name):
                out = br.compare(*self.dirs([result("A", "x", 1)] * 3, [b] * 3))
                self.assertIn("not comparable", out)
                self.assertIn(name, out)

    def test_few_runs_and_incomplete_coverage(self):
        out = br.compare(*self.dirs([result("A", "x", 1000)], [result("B", "y", 0, coverage=(1, 2))]))
        self.assertIn("fewer than 3 runs", out)
        self.assertIn("incomplete", out)
        self.assertNotIn("fewer tokens", out)

    def test_cli(self):
        a, b = self.dirs([result("A", "x", 1000)] * 3, [result("B", "y", 900)] * 3)
        p = subprocess.run([sys.executable, os.path.join(REPO, "templates", "orchestrator", "scripts", "telemetry.py"),
                            "benchmark", a, b], capture_output=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(b"## Quality", p.stdout)

    def test_report_imports(self):
        import ast
        with open(os.path.join(REPO, "templates", "orchestrator", "scripts", "benchmark_report.py")) as f:
            tree = ast.parse(f.read())
        names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        self.assertLessEqual(names, {"json", "os", "statistics"})


class NoModelCalls(unittest.TestCase):
    def test_only_run_command_names_claude(self):
        import ast
        with open(os.path.join(REPO, "scripts", "benchmark.py")) as f:
            tree = ast.parse(f.read())
        where = set()  # functions that build a command running the claude binary
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef):
                for n in ast.walk(fn):
                    if isinstance(n, ast.List) and n.elts and isinstance(n.elts[0], ast.Constant) \
                            and n.elts[0].value == "claude":
                        where.add(fn.name)
        self.assertEqual(where, {"run_command"})


if __name__ == "__main__":
    unittest.main()
