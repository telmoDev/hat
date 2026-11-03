"""Unit tests for T6: usage, metrics and run reports (reports.py), read-only over the telemetry store.
Expected figures are worked out by hand from the fixture below.
  python3 -m unittest discover -s tests
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
SCRIPTS = os.path.join(os.path.dirname(HERE), "templates", "orchestrator", "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)
import reports as rp  # noqa: E402
import telemetry as t  # noqa: E402
from test_odd_tasks import TASK_FILE  # noqa: E402

SONNET, HAIKU = "claude-sonnet-5-5", "claude-haiku-5-5"
RATE = {"provider": "anthropic", "model": SONNET, "currency": "USD", "input": "3", "output": "15",
        "cache_read": "0.30", "cache_write": "3.75", "effective_from": "2026-01-01",
        "source": "https://example.invalid/pricing"}  # made-up figures

# Fixture, worked by hand:
#   run r1 (finished, wall 600 s): a1 and a2 overlap (10:01-10:03, 10:02-10:05) on login#T1, both with usage;
#     a3 on login#T2 finished without usage; a4 never finished (unfinished); a failed launch on login#T2.
#   run r2 (still open): a5 on login#T3, in progress.
#   Task file: T1 done with O1 and O2 passed, T2 blocked, T3 in progress; T2 and T3 have no criteria.


def build(s, root):
    def ev(kind, run, at, inv=None, task=None, key=None, **p):
        s.record(t.make_event(kind, run, task_id=task, invocation_id=inv, timestamp="2026-11-03T%sZ" % at,
                              key=key, payload=p))

    def agent(run, aid, agent, model, task, start, end=None, usage=None):
        ev("agent.started", run, start, "claude:" + aid, task, agent_id=aid, agent_type=agent, model=model,
           runtime="claude-code")
        if end:
            ev("agent.completed", run, end, "claude:" + aid, task)
        if usage == "unavailable":
            ev("usage.reported", run, end, "claude:" + aid, key="u", source="unavailable", reason="x")
        elif usage:
            i, o, cr, cw = usage
            ev("usage.reported", run, end, "claude:" + aid, key="u", source="runtime_reported", model=model,
               input_tokens=i, output_tokens=o, cache_read_tokens=cr, cache_write_tokens=cw, requests=1)

    ev("run.started", "claude:r1", "10:00:00", runtime="claude-code", project_id="ws")
    agent("claude:r1", "a1", "api-dev", SONNET, "login#T1", "10:01:00", "10:03:00", (10, 100, 1000, 50))
    agent("claude:r1", "a2", "api-dev", SONNET, "login#T1", "10:02:00", "10:05:00", (20, 200, 2000, 100))
    agent("claude:r1", "a3", "web-dev", HAIKU, "login#T2", "10:04:00", "10:06:00", "unavailable")
    agent("claude:r1", "a4", "explorer", HAIKU, None, "10:07:00")
    ev("agent.failed", "claude:r1", "10:08:00", "claude:tool:toolu_1", "login#T2", agent_type="web-dev",
       runtime="claude-code", status="failed", error="error")
    ev("run.completed", "claude:r1", "10:10:00", status="completed")
    ev("run.started", "claude:r2", "11:00:00", runtime="claude-code", project_id="ws")
    agent("claude:r2", "a5", "api-dev", SONNET, "login#T3", "11:01:00")
    os.makedirs(os.path.join(root, "odd", "tasks"))
    with open(os.path.join(root, "odd", "tasks", "login.md"), "w", encoding="utf-8") as f:
        f.write(TASK_FILE)
    t.sync_criteria(s, root, now="2026-11-03T12:00:00Z")


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.s = t.Store(os.path.join(self.root, "t.db"))
        build(self.s, self.root)
        self.rates = os.path.join(self.root, "rates.json")
        with open(self.rates, "w") as f:
            json.dump({"version": "test-1", "rates": [RATE]}, f)
        self.norates = os.path.join(self.root, "none.json")

    def tearDown(self):
        self.s.close()
        shutil.rmtree(self.root, ignore_errors=True)


class Usage(Base):
    def test_by_agent_counts_finished_without_usage_in_coverage_only(self):
        out = rp.usage(self.s.db, {}, "agent")
        self.assertIn("| Agent | Invocations | Coverage | Input | Output | Cache read | Cache write | Total |", out)
        self.assertIn("| api-dev | 3 | 2/2 | 30 | 300 | 3,000 | 150 | 3,480 |", out)
        self.assertIn("| web-dev | 1 | 0/1 | — | — | — | — | — |", out)  # finished, no usage: n/a, not 0
        self.assertIn("| explorer | 1 | 0/0 | — | — | — | — | — |", out)

    def test_default_groups_by_agent_and_model(self):
        self.assertIn("| api-dev · %s | 3 | 2/2 |" % SONNET, rp.usage(self.s.db, {}, None))

    def test_filters(self):
        out = rp.usage(self.s.db, {"task": "login#T1"}, "task")
        self.assertIn("| login#T1 | 2 | 2/2 | 30 | 300 | 3,000 | 150 | 3,480 |", out)
        self.assertNotIn("login#T2", out)
        self.assertIn("| claude:r2 | 1 | 0/0 |", rp.usage(self.s.db, {"since": "2026-11-03T10:30:00Z"}, "run"))
        self.assertIn("| ws | 5 |", rp.usage(self.s.db, {"project": "ws"}, "project"))
        self.assertIn("No agent runs match", rp.usage(self.s.db, {"model": "nope"}, "agent"))

    def test_an_unverified_runtime_gives_no_comparable_total(self):
        self.s.record(t.make_event("agent.started", "codex:c1", invocation_id="codex:x1", payload={
            "agent_id": "x1", "agent_type": "worker", "runtime": "codex", "model": "m"}))
        self.s.record(t.make_event("agent.completed", "codex:c1", invocation_id="codex:x1"))
        self.s.record(t.make_event("usage.reported", "codex:c1", invocation_id="codex:x1", key="u", payload={
            "source": "runtime_reported", "model": "m", "input_tokens": 5, "output_tokens": 5}))
        out = rp.usage(self.s.db, {}, "runtime")
        self.assertIn("| codex | 1 | 1/1 | — | — | — | — | — |", out)
        self.assertIn("usage semantics not verified", out)


class Metrics(Base):
    def test_performance(self):
        out = rp.metrics(self.s.db, {}, "runtime", self.norates)
        self.assertIn("| Runtime | Runs | Run wall time (median) | Delegations | Failed launches | In progress | "
                      "Unfinished | Succeeded | Retries | Re-invocations | Agent time (median) | "
                      "Agent time (cumulative) |", out)
        self.assertIn("| claude-code | 2 | 600.0 s | 5 | 1 | 1 | 1 | 3/3 (100%) | 0 | 1 | 120.0 s | 420.0 s |", out)

    def test_parallel_agents_are_not_wall_time(self):
        out = rp.metrics(self.s.db, {"task": "login#T1"}, "task", self.norates)
        # a1 + a2 = 120 s + 180 s cumulative, though they ran within 10:01-10:05 of a 600 s run
        self.assertIn("| login#T1 | 1 | 600.0 s | 2 | 0 | 0 | 0 | 2/2 (100%) | 0 | 1 | 150.0 s | 300.0 s |", out)
        self.assertIn("cumulative agent time adds up agents that ran in parallel", out)

    def test_no_finished_delegations_no_rate(self):
        out = rp.metrics(self.s.db, {"agent": "explorer"}, "agent", self.norates)
        self.assertIn("| 0/0 (no data) |", out)
        self.assertNotIn("100%", out)

    def test_quality_keeps_tasks_without_criteria_apart(self):
        out = rp.metrics(self.s.db, {}, "runtime", self.norates)
        self.assertIn("| Runtime | Tasks | With criteria | Without criteria | Criteria passed | Criteria failed | "
                      "Tasks done | Tasks blocked |", out)
        self.assertIn("| claude-code | 3 | 1 | 2 | 2 | 0 | 1 | 1 |", out)
        self.assertIn("A task without criteria is not a failed one", out)

    def test_partial_coverage_blocks_efficiency_and_cost(self):
        out = rp.metrics(self.s.db, {}, "runtime", self.rates)
        self.assertIn("| claude-code | 2/3 | 1/3 | incomplete | incomplete | 0.00 | incomplete |", out)

    def test_complete_coverage_shows_efficiency_and_estimated_cost(self):
        out = rp.metrics(self.s.db, {"task": "login#T1"}, "task", self.rates)
        # 3,480 tokens / 1 task done; / 2 criteria passed; cost (2017.5 + 4035) per million = 0.0060525
        self.assertIn("| login#T1 | 2/2 | 1/1 | 3,480 | 1,740 | 0.00 | USD 0.0061 |", out)
        self.assertIn("API-equivalent (estimated, combined cache-write rate)", out)
        self.assertIn("not what a subscription", out)
        self.assertIn("| login#T1 | 2/2 | 1/1 | 3,480 | 1,740 | 0.00 | no rates |",
                      rp.metrics(self.s.db, {"task": "login#T1"}, "task", self.norates))

    def test_overhead(self):
        self.s.db.execute("DELETE FROM ingest_log")
        for ms, ok in ((5, 1), (6, 1), (7, 1), (100, 0)):
            self.s.db.execute("INSERT INTO ingest_log (at, command, events, recorded, elapsed_ms, ok) "
                              "VALUES ('2026-11-03T10:00:00.000Z', 'hook claude', 1, 1, ?, ?)", (ms, ok))
        out = rp.metrics(self.s.db, {}, "runtime", self.norates)
        self.assertIn("Hook calls 4 · errors 1 · in-process median 6.5 ms · p95 100.0 ms", out)


class RunsWithoutAgents(Base):
    """A session that launched no agent is still a run: it counts where runs can be grouped (runtime, project,
    run) and is reported apart where they can't (agent, model, task)."""

    def setUp(self):
        super().setUp()
        self.s.record(t.make_event("run.started", "claude:r3", timestamp="2026-11-03T12:00:00Z",
                                   payload={"runtime": "claude-code", "project_id": "ws"}))
        self.s.record(t.make_event("run.completed", "claude:r3", timestamp="2026-11-03T12:00:05Z",
                                   payload={"status": "completed"}))

    def test_counted_by_runtime_project_and_run(self):
        out = rp.metrics(self.s.db, {}, "runtime", self.norates)
        self.assertIn("| claude-code | 3 | 302.5 s | 5 |", out)  # wall median of 600 s and 5 s
        self.assertIn("| ws | 3 |", rp.metrics(self.s.db, {}, "project", self.norates))
        self.assertIn("| claude:r3 | 1 | 5.0 s | 0 | 0 | 0 | 0 | 0/0 (no data) |",
                      rp.metrics(self.s.db, {}, "run", self.norates))

    def test_reported_apart_by_agent(self):
        out = rp.metrics(self.s.db, {}, "agent", self.norates)
        self.assertIn("Runs: 3, of which 1 had no agent runs (not in the rows above)", out)

    def test_left_out_by_agent_level_filters(self):
        out = rp.metrics(self.s.db, {"agent": "api-dev"}, "runtime", self.norates)
        self.assertIn("| claude-code | 2 |", out)
        self.assertIn("Runs without agent runs are left out by the agent, model, task or status filter (1 here)", out)

    def test_only_runs_without_agents(self):
        s = t.Store(os.path.join(self.root, "only.db"))
        self.addCleanup(s.close)
        s.record(t.make_event("run.started", "claude:e1", timestamp="2026-11-03T12:00:00Z",
                              payload={"runtime": "claude-code", "project_id": "ws"}))
        out = rp.metrics(s.db, {}, "runtime", self.norates)
        self.assertIn("| claude-code | 1 | — | 0 |", out)  # still open: no wall time yet


class MainSessionInReports(Base):
    """The orchestrator's own session shows apart: never a delegation, never in agent coverage."""

    def setUp(self):
        super().setUp()
        rec = lambda kind, at, **p: self.s.record(t.make_event(kind, "claude:r1", invocation_id="claude:r1:main",
                                                               timestamp="2026-11-03T%sZ" % at, key=kind, payload=p))
        rec("agent.started", "10:00:00", agent_type="main", runtime="claude-code")
        rec("agent.completed", "10:10:00", agent_type="main", runtime="claude-code")
        rec("usage.reported", "10:10:00", source="runtime_reported", model=SONNET, input_tokens=5, output_tokens=50,
            cache_read_tokens=500, cache_write_tokens=20, requests=3)

    def test_usage_has_a_main_row(self):
        self.assertIn("| main | 1 | 1/1 | 5 | 50 | 500 | 20 | 575 |", rp.usage(self.s.db, {}, "agent"))

    def test_metrics_keep_delegations_as_they_were_and_show_the_main_session(self):
        out = rp.metrics(self.s.db, {}, "runtime", self.norates)
        self.assertIn("| claude-code | 2 | 600.0 s | 5 | 1 | 1 | 1 | 3/3 (100%) | 0 | 1 | 120.0 s | 420.0 s |", out)
        self.assertIn("| Runtime | Sessions | Main usage | Input | Output | Cache read | Cache write | Total |", out)
        self.assertIn("| claude-code | 2 | 1/2 | 5 | 50 | 500 | 20 | 575 |", out)

    def test_the_run_report_shows_the_main_session_apart(self):
        out = rp.report(self.s.db, "claude:r1", self.norates)
        self.assertIn("| main | main | — | %s | completed |" % SONNET, out)
        self.assertIn("Coverage 2/3", out)  # agent runs only
        self.assertIn("Main session tokens 575 · agent runs tokens 3,480", out)


class RunReport(Base):
    def test_one_run(self):
        out = rp.report(self.s.db, "claude:r1", self.norates)
        self.assertIn("# Run claude:r1", out)
        self.assertIn("Status completed · wall time 600.0 s · runtime claude-code · project ws", out)
        self.assertIn("| a4 | explorer | — | %s | unfinished |" % HAIKU, out)
        self.assertIn("| toolu_1 | web-dev | login#T2 | — | failed launch |", out)
        self.assertIn("Criteria of the tasks this run worked on (not attributed to the run)", out)
        self.assertIn("| login#T1 | done | O1 passed · O2 passed |", out)
        self.assertIn("| login#T2 | blocked | no criteria recorded |", out)
        self.assertIn("Coverage 2/3", out)

    def test_last_is_the_latest_run(self):
        self.assertIn("# Run claude:r2", rp.report(self.s.db, "last", self.norates))
        self.assertIn("| a5 | api-dev | login#T3 | %s | in progress |" % SONNET,
                      rp.report(self.s.db, "last", self.norates))

    def test_unknown_run(self):
        self.assertIsNone(rp.report(self.s.db, "claude:nope", self.norates))


class Cli(unittest.TestCase):
    def run_cli(self, *args, db):
        env = dict(os.environ, ORCH_TELEMETRY_DB=db, ORCH_RATES=os.path.join(os.path.dirname(db), "none.json"))
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, "telemetry.py")] + list(args),
                              capture_output=True, env=env, timeout=60)

    def test_commands(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        db = os.path.join(root, "t.db")
        p = self.run_cli("metrics", db=db)
        self.assertEqual((p.returncode, b"No telemetry recorded yet" in p.stdout), (0, True))
        s = t.Store(db)
        build(s, root)
        s.close()
        for args, want in ((["usage", "--by", "agent"], b"| api-dev | 3 | 2/2 |"),
                           (["metrics", "--task", "login#T1", "--by", "task"], b"| login#T1 | 2/2 | 1/1 |"),
                           (["report", "last"], b"# Run claude:r2")):
            with self.subTest(args):
                p = self.run_cli(*args, db=db)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn(want, p.stdout)
        self.assertEqual(self.run_cli("report", "claude:nope", db=db).returncode, 1)
        self.assertEqual(self.run_cli("usage", "--by", "colour", db=db).returncode, 2)


class Benchmark(unittest.TestCase):
    def test_10k_invocations_each_report_under_1_s(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        s = t.Store(os.path.join(root, "t.db"))
        self.addCleanup(s.close)
        db = s.db
        db.execute("BEGIN")
        for r in range(1000):
            db.execute("INSERT INTO runs (run_id, project_id, runtime, started_at, finished_at, status, "
                       "total_duration_ms) VALUES (?, 'ws', 'claude-code', '2026-11-03T10:00:00.000Z', "
                       "'2026-11-03T11:00:00.000Z', 'completed', 3600000)", ("r%d" % r,))
        for i in range(10000):
            task = "f%d#T%d" % (i % 2000 // 4, i % 4 + 1)
            db.execute("INSERT INTO agent_invocations (invocation_id, run_id, task_id, agent_id, agent_type, runtime, "
                       "model, started_at, finished_at, status, duration_ms, retry_number) VALUES (?, ?, ?, ?, ?, "
                       "'claude-code', ?, '2026-11-03T10:00:00.000Z', '2026-11-03T10:01:00.000Z', 'completed', "
                       "60000, 0)", ("i%d" % i, "r%d" % (i % 1000), task, "i%d" % i, "dev%d" % (i % 5), SONNET))
            db.execute("INSERT INTO usage_records (usage_id, invocation_id, run_id, model, input_tokens, output_tokens, "
                       "cache_read_tokens, cache_write_tokens, source) VALUES (?, ?, ?, ?, 1, 2, 3, 4, "
                       "'runtime_reported')", ("u%d" % i, "i%d" % i, "r%d" % (i % 1000), SONNET))
        for k in range(2000):
            db.execute("INSERT INTO tasks (task_id, status) VALUES (?, 'done')", ("f%d#T%d" % (k // 4, k % 4 + 1),))
            db.execute("INSERT INTO criteria (criterion_id, task_id, criterion_code, status) VALUES (?, ?, 'O1', "
                       "'passed')", ("c%d" % k, "f%d#T%d" % (k // 4, k % 4 + 1)))
        db.execute("COMMIT")
        timings = {}
        for name, call in (("usage", lambda: rp.usage(db, {}, None)),
                           ("metrics", lambda: rp.metrics(db, {}, "agent", os.path.join(root, "none.json"))),
                           ("metrics by task", lambda: rp.metrics(db, {}, "task", os.path.join(root, "none.json"))),
                           ("report", lambda: rp.report(db, "r1", os.path.join(root, "none.json")))):
            start = time.perf_counter()
            call()
            timings[name] = (time.perf_counter() - start) * 1000
        print("\nbenchmark T6: 10,000 invocations, " + ", ".join("%s %.0f ms" % kv for kv in timings.items()))
        for name, ms in timings.items():
            self.assertLess(ms, 1000, name)


class NoModelOrNetwork(unittest.TestCase):
    def test_reports_imports(self):
        import ast
        with open(os.path.join(SCRIPTS, "reports.py")) as f:
            tree = ast.parse(f.read())
        names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        self.assertLessEqual(names, {"api_cost", "datetime", "decimal", "statistics"})


if __name__ == "__main__":
    unittest.main()
