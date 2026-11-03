"""Unit tests for the telemetry core: the event contract, the SQLite store and the non-blocking hook entry.
  python3 -m unittest discover -s tests
Standard library only, like the scripts they test. tests/smoke.sh runs them on macOS, Linux and Windows.
"""
import ast
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(os.path.dirname(HERE), "templates", "orchestrator")
sys.path.insert(0, os.path.join(TPL, "scripts"))
import telemetry as t  # noqa: E402

# On Windows a bare "bash" can resolve to WSL's in System32 before Git Bash: take the one on PATH.
BASH = shutil.which("bash")


def ev(event_type, run="claude:s1", task=None, inv=None, ts="2026-11-03T15:30:00Z", key=None, **payload):
    return t.make_event(event_type, run, task_id=task, invocation_id=inv, payload=payload, timestamp=ts, key=key)


class Contract(unittest.TestCase):
    def test_event_id_is_deterministic(self):
        a = ev("agent.started", inv="claude:a1", agent_type="api-dev", runtime="claude-code")
        b = ev("agent.started", inv="claude:a1", agent_type="api-dev", runtime="claude-code")
        self.assertEqual(a["event_id"], b["event_id"])
        self.assertNotEqual(a["event_id"], ev("agent.started", inv="claude:a2", agent_type="api-dev")["event_id"])
        self.assertEqual(a["schema_version"], t.SCHEMA_VERSION)

    def test_timestamps_are_normalized_to_utc(self):
        e = t.validate(ev("run.started", ts="2026-11-03T17:30:00+02:00", runtime="claude-code"))
        self.assertEqual(e["timestamp"], "2026-11-03T15:30:00.000Z")

    def test_rejects(self):
        cases = {
            "unknown type": dict(ev("run.started", runtime="claude-code"), event_type="run.paused"),
            "no run": dict(ev("run.started", runtime="claude-code"), run_id=""),
            "naive timestamp": dict(ev("run.started", runtime="claude-code"), timestamp="2026-11-03T15:30:00"),
            "payload key outside the contract (privacy)": ev("agent.completed", inv="claude:a1", prompt="secret"),
            "agent event without invocation": ev("agent.started", agent_type="api-dev"),
            "tokens with source unavailable": ev("usage.reported", inv="claude:a1", source="unavailable", input_tokens=5),
            "negative tokens": ev("usage.reported", inv="claude:a1", source="runtime_reported", input_tokens=-1),
            "unknown source": ev("usage.reported", inv="claude:a1", source="guessed"),
            "unknown criterion status": ev("criterion.verified", task="f#T1", criterion_code="O1", status="ok"),
            "long string": ev("agent.completed", inv="claude:a1", status="success", error="x" * 500),
        }
        for name, e in cases.items():
            with self.subTest(name):
                self.assertRaises(ValueError, t.validate, e)


class Store(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "telemetry.db")
        self.s = t.Store(self.path)

    def tearDown(self):
        self.s.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def one(self, sql, *args):
        return self.s.db.execute(sql, args).fetchone()

    def test_migrations_are_versioned_and_idempotent(self):
        self.s.close()
        self.s = t.Store(self.path)
        self.assertEqual([r[0] for r in self.s.db.execute("SELECT version FROM schema_migrations")], [1, 2])

    def test_each_session_is_its_own_run(self):  # F1-01
        self.s.record(ev("run.started", run="claude:s1", runtime="claude-code", project_id="ws"))
        self.s.record(ev("run.started", run="claude:s2", runtime="claude-code", project_id="ws"))
        self.assertEqual(self.one("SELECT count(DISTINCT run_id) FROM runs")[0], 2)

    def test_run_lifecycle(self):  # F1-03
        self.s.record(ev("run.started", runtime="claude-code", project_id="ws", orchestrator_version="0.8.0"))
        self.s.record(ev("run.completed", ts="2026-11-03T15:31:00Z", status="completed"))
        row = self.one("SELECT status, started_at, finished_at, total_duration_ms, orchestrator_version FROM runs")
        self.assertEqual(row, ("completed", "2026-11-03T15:30:00.000Z", "2026-11-03T15:31:00.000Z", 60000, "0.8.0"))

    def test_resumed_or_compacted_session_keeps_its_run(self):
        self.s.record(ev("run.started", runtime="claude-code", source="startup"))
        self.s.record(ev("run.completed", ts="2026-11-03T15:31:00Z", status="completed"))
        self.s.record(ev("run.started", ts="2026-11-03T16:00:00Z", runtime="claude-code", source="resume"))
        row = self.one("SELECT status, started_at, finished_at, starts FROM runs")
        self.assertEqual(row, ("running", "2026-11-03T15:30:00.000Z", None, 2))

    def test_invocations_belong_to_their_run_and_task(self):  # F1-02
        self.s.record(ev("run.started", runtime="claude-code"))
        self.s.record(ev("agent.started", task="login#T1", inv="claude:a1", agent_type="api-dev", runtime="claude-code"))
        self.s.record(ev("agent.completed", task="login#T1", inv="claude:a1", ts="2026-11-03T15:30:45Z",
                         status="success", model="claude-sonnet-5-5"))
        row = self.one("SELECT run_id, task_id, agent_type, model, status, duration_ms, duration_source "
                       "FROM agent_invocations")
        self.assertEqual(row, ("claude:s1", "login#T1", "api-dev", "claude-sonnet-5-5", "success", 45000, "calculated"))
        self.assertEqual(self.one("SELECT task_id, run_id FROM tasks"), ("login#T1", "claude:s1"))

    def test_a_stop_without_its_start_still_records_the_invocation(self):
        self.s.record(ev("agent.completed", inv="claude:a1", status="success"))
        self.assertEqual(self.one("SELECT status, duration_ms FROM agent_invocations"), ("success", None))

    def test_duplicate_events_count_once(self):
        e = ev("usage.reported", inv="claude:a1", key="claude-sonnet-5-5", source="runtime_reported",
               model="claude-sonnet-5-5", input_tokens=10, output_tokens=5)
        self.assertTrue(self.s.record(e))
        self.assertFalse(self.s.record(dict(e)))
        self.assertEqual(self.one("SELECT count(*) FROM usage_records")[0], 1)
        self.assertEqual(self.one("SELECT count(*) FROM events")[0], 1)

    def test_unavailable_usage_is_recorded_with_null_tokens(self):  # F1-04, F1-05
        self.s.record(ev("usage.reported", inv="claude:a1", source="unavailable", reason="background agent"))
        self.assertEqual(self.one("SELECT source, input_tokens, output_tokens FROM usage_records"),
                         ("unavailable", None, None))

    def test_criteria_keep_their_last_result(self):
        self.s.record(ev("criterion.verified", task="login#T1", key="O1@1", criterion_code="O1", status="failed",
                         verification_method="command"))
        self.s.record(ev("criterion.verified", task="login#T1", key="O1@2", ts="2026-11-03T16:00:00Z",
                         criterion_code="O1", status="passed", verification_method="command"))
        self.assertEqual(self.one("SELECT criterion_id, status FROM criteria"), ("login#T1#O1", "passed"))

    def test_data_survives_closing(self):  # F1-09
        self.s.record(ev("run.started", runtime="claude-code"))
        self.s.close()
        self.s = t.Store(self.path)
        self.assertEqual(self.one("SELECT count(*) FROM runs")[0], 1)


class HookEntry(unittest.TestCase):
    """The hook entry never fails the session and never prints (a SessionStart hook's output becomes context)."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        o = os.path.join(self.root, ".orchestrator")
        for sub in ("scripts", "hooks"):
            os.makedirs(os.path.join(o, sub))
        shutil.copy(os.path.join(TPL, "scripts", "telemetry.py"), os.path.join(o, "scripts"))
        shutil.copy(os.path.join(TPL, "hooks", "telemetry.sh"), os.path.join(o, "hooks"))
        self.conf = os.path.join(o, "orchestrator.conf")
        with open(self.conf, "w") as f:
            f.write('REPOS="."\n')
        self.db = os.path.join(o, "telemetry", "telemetry.db")
        self.errors = os.path.join(o, "telemetry", "errors.log")
        self.script = os.path.join(o, "hooks", "telemetry.sh").replace("\\", "/")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def hook(self, stdin):
        p = subprocess.run([BASH, self.script, "ingest"], input=stdin.encode(), capture_output=True, timeout=60)
        return p.returncode, p.stdout

    def count(self, table):
        with sqlite3.connect(self.db) as db:
            return db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def test_records_and_measures_its_own_overhead(self):
        self.assertEqual(self.hook(json.dumps(ev("run.started", runtime="claude-code"))), (0, b""))
        self.assertEqual(self.count("runs"), 1)
        with sqlite3.connect(self.db) as db:
            ok, ms = db.execute("SELECT ok, elapsed_ms FROM ingest_log").fetchone()
        self.assertEqual(ok, 1)
        self.assertGreaterEqual(ms, 0)

    def test_bad_input_is_logged_not_raised(self):  # F1-10
        self.assertEqual(self.hook("{not json"), (0, b""))
        self.assertEqual(self.hook(json.dumps(ev("agent.completed", inv="claude:a1", prompt="x"))), (0, b""))
        with open(self.errors) as f:
            log = f.read()
        self.assertEqual(len(log.splitlines()), 2)
        self.assertNotIn('"x"', log)  # the rejected payload is not copied into the log

    def test_a_corrupt_database_does_not_block(self):  # F1-10
        os.makedirs(os.path.dirname(self.db))
        with open(self.db, "wb") as f:
            f.write(b"this is not sqlite" * 100)
        self.assertEqual(self.hook(json.dumps(ev("run.started", runtime="claude-code"))), (0, b""))
        self.assertTrue(os.path.getsize(self.errors) > 0)

    def test_off_records_nothing(self):
        with open(self.conf, "a") as f:
            f.write('TELEMETRY="off"\n')
        self.assertEqual(self.hook(json.dumps(ev("run.started", runtime="claude-code"))), (0, b""))
        self.assertFalse(os.path.exists(self.db))

    def test_no_python_does_not_block(self):
        env = dict(os.environ, PATH=os.path.dirname(BASH))
        if any(shutil.which(c, path=env["PATH"]) for c in ("python3", "python", "py")):
            self.skipTest("python lives next to bash here")
        p = subprocess.run([BASH, self.script, "ingest"], input=b"{}", capture_output=True, env=env, timeout=60)
        self.assertEqual((p.returncode, p.stdout), (0, b""))


class NoModelOrNetwork(unittest.TestCase):  # F1-13
    def test_imports_only_local_modules(self):
        allowed = {"datetime", "hashlib", "json", "os", "re", "sqlite3", "sys", "time", "claude_transcript"}
        for script in ("telemetry.py", "claude_transcript.py"):
            with open(os.path.join(TPL, "scripts", script)) as f:
                tree = ast.parse(f.read())
            names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
            names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
            self.assertLessEqual(names, allowed, script)


if __name__ == "__main__":
    unittest.main()
