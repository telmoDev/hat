"""Unit tests for T5: the ODD task files' criteria and task statuses projected into the telemetry store.
The Markdown stays the source of truth: the store keeps a projection, never writes back.
  python3 -m unittest discover -s tests
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "templates", "orchestrator", "scripts"))
sys.path.insert(0, HERE)
import telemetry as t  # noqa: E402
from test_odd_tasks import TASK_FILE  # noqa: E402


class Sync(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "odd", "tasks"))
        self.path = os.path.join(self.root, "odd", "tasks", "login.md")
        self.write(TASK_FILE)
        self.s = t.Store(os.path.join(self.root, "t.db"))

    def tearDown(self):
        self.s.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, body):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(body)

    def add_evidence(self, line):
        with open(self.path, encoding="utf-8") as f:
            body = f.read()
        self.write(body.replace("\n## Run log", line + "\n\n## Run log"))

    def sync(self, run=None, phase="manual", at="2026-11-03T10:00:00Z"):
        return t.sync_criteria(self.s, self.root, run, phase, now=at)

    def criteria(self):
        return self.s.db.execute("SELECT criterion_id, status, verification_method, verified_at, run_id FROM criteria "
                                 "ORDER BY criterion_id").fetchall()

    def test_each_criterion_keeps_its_last_result(self):  # F1-08
        self.sync()
        self.assertEqual(self.criteria(), [
            ("login#T1#O1", "passed", "command", "2026-11-02T00:00:00.000Z", None),
            ("login#T1#O2", "passed", "command", "2026-11-02T00:00:00.000Z", None),
        ])

    def test_a_second_sync_records_nothing(self):
        self.sync()
        n = self.s.db.execute("SELECT count(*) FROM events").fetchone()[0]
        self.sync(at="2026-11-03T11:00:00Z")
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM events").fetchone()[0], n)

    def test_a_later_failure_on_the_same_day_wins(self):
        self.sync()
        self.add_evidence("- 2026-11-02 T1 · O1 · `pytest tests/test_login.py::test_valid` → failed: regression")
        self.sync(at="2026-11-03T11:00:00Z")
        self.assertEqual(self.criteria()[0][:2], ("login#T1#O1", "failed"))

    def test_an_inserted_line_does_not_replay_older_results(self):
        self.sync()
        with open(self.path, encoding="utf-8") as f:
            body = f.read()
        self.write(body.replace("## Evidence\n", "## Evidence\n- 2026-10-30 T0 · O9 · `x` → failed: early\n"))
        self.sync(at="2026-11-03T11:00:00Z")
        self.assertEqual({r[0]: r[1] for r in self.criteria()}["login#T1#O1"], "passed")

    def test_task_statuses_and_titles_come_from_the_tasks_table(self):
        self.sync()
        rows = self.s.db.execute("SELECT task_id, title, status, run_id FROM tasks ORDER BY task_id").fetchall()
        self.assertEqual(rows, [("login#T1", "login endpoint", "done", None),
                                ("login#T2", "login form", "blocked", None),
                                ("login#T3", "docs", "in_progress", None)])

    def test_criteria_link_to_invocations_through_the_task(self):  # F1-08
        self.s.record(t.make_event("agent.started", "claude:s1", task_id="login#T1", invocation_id="claude:a1",
                                   payload={"agent_type": "api-dev", "agent_id": "a1"}))
        self.sync()
        row = self.s.db.execute("SELECT i.invocation_id, c.criterion_code, c.status FROM agent_invocations i "
                                "JOIN criteria c ON c.task_id = i.task_id ORDER BY c.criterion_code").fetchall()
        self.assertEqual(row, [("claude:a1", "O1", "passed"), ("claude:a1", "O2", "passed")])

    def test_no_command_or_output_reaches_the_store(self):
        self.sync()
        dump = json.dumps(self.s.db.execute("SELECT payload_json FROM events").fetchall())
        for text in ("pytest", "AssertionError", "1 passed", "mkdocs"):
            self.assertNotIn(text, dump)


class Attribution(Sync):
    """criteria.run_id names a run only when that run is shown to have logged the evidence: the line appeared
    between the run's own start and end syncs, and no other run had a start sync open."""

    def test_history_is_never_attributed(self):
        self.sync("claude:s1", "start")
        self.sync("claude:s1", "end", at="2026-11-03T10:30:00Z")
        self.assertEqual({r[4] for r in self.criteria()}, {None})

    def test_evidence_logged_during_the_run_is_attributed(self):
        self.sync("claude:s1", "start")
        self.add_evidence("- 2026-11-03 T2 · O3 · `npm test -- form` → passed: 3 passed")
        self.sync("claude:s1", "end", at="2026-11-03T10:30:00Z")
        attributed = {r[0]: r[4] for r in self.criteria()}
        self.assertEqual(attributed, {"login#T1#O1": None, "login#T1#O2": None, "login#T2#O3": "claude:s1"})

    def test_no_start_sync_means_no_attribution(self):
        self.sync("claude:s1", "start")
        self.add_evidence("- 2026-11-03 T2 · O3 · `npm test -- form` → passed: 3 passed")
        self.sync("claude:s2", "end", at="2026-11-03T10:30:00Z")  # s2 never synced at its start
        self.assertIsNone(dict((r[0], r[4]) for r in self.criteria())["login#T2#O3"])

    def test_two_open_runs_mean_no_attribution(self):
        self.sync("claude:s1", "start")
        self.sync("claude:s2", "start", at="2026-11-03T10:05:00Z")
        self.add_evidence("- 2026-11-03 T2 · O3 · `npm test -- form` → passed: 3 passed")
        self.sync("claude:s1", "end", at="2026-11-03T10:30:00Z")
        self.assertIsNone(dict((r[0], r[4]) for r in self.criteria())["login#T2#O3"])

    def test_a_manual_sync_attributes_nothing(self):
        self.add_evidence("- 2026-11-03 T2 · O3 · `npm test -- form` → passed: 3 passed")
        self.sync()
        self.assertEqual({r[4] for r in self.criteria()}, {None})


class Hooks(unittest.TestCase):
    def test_session_start_and_end_sync_the_criteria(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, "odd", "tasks"))
        path = os.path.join(root, "odd", "tasks", "login.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(TASK_FILE)
        s = t.Store(os.path.join(root, "t.db"))
        self.addCleanup(s.close)
        start = {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"}
        t.claude_hook(s, start, {}, "ws", now="2026-11-03T10:00:00Z", root=root)
        with open(path, encoding="utf-8") as f:
            body = f.read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(body.replace("\n## Run log", "- 2026-11-03 T2 · O3 · `npm test` → passed: ok\n\n## Run log"))
        t.claude_hook(s, {"hook_event_name": "SessionEnd", "session_id": "s1"}, {}, "ws", now="2026-11-03T10:30:00Z",
                      root=root)
        self.assertEqual(s.db.execute("SELECT run_id FROM criteria WHERE criterion_code = 'O3'").fetchone()[0],
                         "claude:s1")


class Benchmark(unittest.TestCase):
    def test_100_task_files_sync_under_200_ms(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, "odd", "tasks"))
        lines = "".join("- 2026-11-02 T%d · O%d · `cmd` → passed: ok\n" % (i % 3 + 1, i + 1) for i in range(10))
        body = TASK_FILE.replace("## Run log", lines + "\n## Run log")
        for i in range(100):
            with open(os.path.join(root, "odd", "tasks", "f%03d.md" % i), "w", encoding="utf-8") as f:
                f.write(body)
        s = t.Store(os.path.join(root, "t.db"))
        self.addCleanup(s.close)
        start = time.perf_counter()
        t.sync_criteria(s, root, None, "manual", now="2026-11-03T10:00:00Z")
        first = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        t.sync_criteria(s, root, None, "manual", now="2026-11-03T11:00:00Z")
        again = (time.perf_counter() - start) * 1000
        print("\nbenchmark T5: 100 task files, first sync %.0f ms, unchanged resync %.0f ms" % (first, again))
        self.assertLess(again, 200)


if __name__ == "__main__":
    unittest.main()
