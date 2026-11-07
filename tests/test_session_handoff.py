"""Tests for S1: the automatic session handoff (templates/orchestrator/scripts/session_handoff.py).
  python3 -m unittest tests.test_session_handoff
Needs git and bash (Git Bash on Windows), like tests/smoke.sh. No network, no model.
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SCRIPTS = os.path.join(REPO, "templates", "orchestrator", "scripts")
BASH = shutil.which("bash")
sys.path.insert(0, SCRIPTS)
import session_handoff as h  # noqa: E402
import telemetry as t  # noqa: E402

TASK = """# checkout

Status: active · Next: T2 wire the coupon into the total
Ticket: — · Repos: api · PRs: —

## Tasks
| ID | Task | Serves | Depends on | Agent · tier | Status |
|---|---|---|---|---|---|
| T1 | coupon model | S1 · O1 | — | api-dev · normal | done |
| T2 | coupon in total | S1 · O2 | T1 | api-dev · normal | in progress |
| T3 | docs | S2 · O3 | T2 | api-dev · trivial | pending |
"""


class Workspace(unittest.TestCase):
    """A workspace root with memory/, a task file and one repo (api) with an origin."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cfg = os.path.join(cls.tmp, "gitconfig")
        with open(cfg, "w") as f:
            f.write("[user]\n\tname = t\n\temail = t@example.com\n[init]\n\tdefaultBranch = main\n"
                    "[commit]\n\tgpgsign = false\n")
        os.environ["GIT_CONFIG_GLOBAL"], os.environ["GIT_CONFIG_NOSYSTEM"] = cfg, "1"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.ws = tempfile.mkdtemp(dir=self.tmp)
        self.write(".orchestrator/orchestrator.conf", 'REPOS="api"\nBASE_BRANCHES="api=main"\nSESSION_HANDOFF="on"\n')
        for name in ("NEXT_STEPS", "PROJECT_STATE", "PROGRESS", "DECISIONS"):
            self.write("memory/%s.md" % name, "# %s\n" % name)
        self.write("odd/tasks/checkout.md", TASK)
        origin, api = os.path.join(self.ws, "origin.git"), os.path.join(self.ws, "api")
        self.git("init", "-q", "--bare", origin)
        self.git("init", "-q", api)
        self.write("api/README.md", "# api\n")
        self.git("-C", api, "add", "-A")
        self.git("-C", api, "commit", "-qm", "init")
        self.git("-C", api, "remote", "add", "origin", origin)
        self.git("-C", api, "push", "-q", "-u", "origin", "main")

    # helpers
    def git(self, *args):
        subprocess.run(["git"] + list(args), check=True, capture_output=True)

    def path(self, rel):
        return os.path.join(self.ws, *rel.split("/"))

    def write(self, rel, text):
        os.makedirs(os.path.dirname(self.path(rel)), exist_ok=True)
        with open(self.path(rel), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def work_in_api(self):
        """A branch with one commit not in origin/main and two uncommitted files."""
        api = self.path("api")
        self.git("-C", api, "checkout", "-q", "-b", "feat/coupon")
        self.write("api/coupon.py", "x = 1\n")
        self.git("-C", api, "add", "-A")
        self.git("-C", api, "commit", "-qm", "feat: coupon")
        self.write("api/cart.py", "y = 2\n")
        self.write("api/notes.txt", "secret: hunter2-do-not-store\n")

    def start(self, sid, at="2026-11-06T10:00:00Z", **extra):
        return h.start(self.ws, dict({"session_id": sid, "hook_event_name": "SessionStart"}, **extra), now=at)

    def end(self, sid, at="2026-11-06T11:00:00Z"):
        return h.end(self.ws, {"session_id": sid, "hook_event_name": "SessionEnd"}, now=at)


class Handoff(Workspace):
    def test_an_unsynced_session_leaves_a_draft_of_where_it_stopped(self):  # O1
        self.start("s1")
        self.work_in_api()
        self.end("s1")
        text = self.start("s2", at="2026-11-06T12:00:00Z")
        self.assertIsNotNone(text)
        self.assertIn("api: on feat/coupon", text)
        self.assertIn("2 uncommitted", text)
        self.assertIn("1 commit not in origin/main", text)
        self.assertIn("odd/tasks/checkout.md", text)
        self.assertIn("T2 wire the coupon into the total", text)
        self.assertIn("open: T2, T3", text)
        self.assertIn("sync-memory", text)

    def test_shown_once(self):  # O2
        self.start("s1")
        self.work_in_api()
        self.end("s1")
        self.assertIsNotNone(self.start("s2", at="2026-11-06T12:00:00Z"))
        self.assertIsNone(self.start("s2", at="2026-11-06T12:05:00Z", source="compact"))

    def test_nothing_after_a_synced_session(self):  # O2
        self.start("s1")
        self.work_in_api()
        self.write("memory/NEXT_STEPS.md", "# NEXT_STEPS\n\n## Resume\n- checkout T2\n")
        self.end("s1")
        self.assertIsNone(self.start("s2", at="2026-11-06T12:00:00Z"))

    def test_nothing_when_there_is_nothing_to_hand_off(self):
        self.write("odd/tasks/checkout.md", TASK.replace("Status: active", "Status: done"))
        self.start("s1")
        self.end("s1")
        self.assertIsNone(self.start("s2", at="2026-11-06T12:00:00Z"))

    def test_a_killed_session_is_recovered_at_the_next_start(self):  # O3
        self.start("s1")
        self.work_in_api()
        # no SessionEnd for s1
        text = self.start("s2", at="2026-11-06T12:00:00Z")
        self.assertIsNotNone(text)
        self.assertIn("api: on feat/coupon", text)
        self.assertIn("still open or ended without its end hook", text)

    def test_a_killed_session_that_synced_is_not_a_draft(self):  # O3
        self.start("s1")
        self.work_in_api()
        self.write("memory/PROGRESS.md", "# PROGRESS\n\n- checkout T2 half done\n")
        self.assertIsNone(self.start("s2", at="2026-11-06T12:00:00Z"))

    def test_a_parallel_session_that_syncs_is_not_left_a_draft(self):
        self.start("a")
        self.work_in_api()
        self.start("b", at="2026-11-06T10:30:00Z")  # a is still open: b may see a's state, worded as possibly open
        self.end("b", at="2026-11-06T10:40:00Z")
        self.write("memory/NEXT_STEPS.md", "# NEXT_STEPS\n\n## Resume\n- checkout T2\n")
        self.end("a", at="2026-11-06T11:00:00Z")  # a synced before ending
        self.assertIsNone(self.start("c", at="2026-11-06T12:00:00Z"))

    def test_a_resumed_session_keeps_its_first_start(self):
        self.start("s1")
        self.write("memory/PROGRESS.md", "# PROGRESS\n\n- synced early\n")
        self.start("s1", at="2026-11-06T10:30:00Z", source="resume")
        self.work_in_api()
        self.end("s1")
        # memory changed since s1's first start, so s1 synced: nothing to show.
        self.assertIsNone(self.start("s2", at="2026-11-06T12:00:00Z"))

    def test_a_session_without_an_id_is_recovered_like_a_killed_one(self):  # Codex: start-side only
        h.start(self.ws, {"hook_event_name": "SessionStart"}, now="2026-11-06T10:00:00Z")
        self.work_in_api()
        text = h.start(self.ws, {"hook_event_name": "SessionStart"}, now="2026-11-06T12:00:00Z")
        self.assertIsNotNone(text)
        self.assertIn("api: on feat/coupon", text)

    def test_agent_runs_that_never_finished(self):
        db = self.path(".orchestrator/telemetry/telemetry.db")
        store = t.Store(db)
        for e in (t.make_event("agent.started", "claude:s1", invocation_id="claude:a1", key="start",
                               timestamp="2026-11-06T10:10:00Z", payload={"agent_type": "api-dev"}),
                  t.make_event("agent.started", "claude:s1", invocation_id="claude:a2", key="start",
                               timestamp="2026-11-06T10:11:00Z", payload={"agent_type": "explorer"}),
                  t.make_event("agent.completed", "claude:s1", invocation_id="claude:a2",
                               timestamp="2026-11-06T10:12:00Z", payload={"agent_type": "explorer"}),
                  t.make_event("agent.started", "claude:s1", invocation_id="claude:s1:main", key="main-start",
                               timestamp="2026-11-06T10:00:00Z", payload={"agent_type": "main"})):
            store.record(e)
        store.close()
        self.start("s1")
        self.end("s1")
        text = self.start("s2", at="2026-11-06T12:00:00Z")
        self.assertIn("agent runs started and not finished: 1 (api-dev)", text)

    def test_off_records_and_shows_nothing(self):
        self.write(".orchestrator/orchestrator.conf", 'REPOS="api"\nSESSION_HANDOFF="off"\n')
        self.start("s1")
        self.work_in_api()
        self.end("s1")
        self.assertIsNone(self.start("s2", at="2026-11-06T12:00:00Z"))
        self.assertFalse(os.path.exists(self.path(".orchestrator/tmp/handoff")))


class Privacy(Workspace):
    def test_no_contents_diffs_or_secrets(self):  # O4
        self.start("s1")
        self.work_in_api()
        self.write("odd/tasks/checkout.md", TASK.replace("Next: T2 wire the coupon into the total",
                                                         "Next: T2 token: abcdef123456 then ship"))
        self.end("s1")
        text = self.start("s2", at="2026-11-06T12:00:00Z")
        self.assertNotIn("hunter2", text)      # file content
        self.assertNotIn("y = 2", text)        # diff
        self.assertNotIn("feat: coupon", text)  # commit message
        self.assertNotIn("abcdef123456", text)  # a secret-looking line is left out
        self.assertIn("left out", text)
        files = os.listdir(self.path(".orchestrator/tmp/handoff"))
        for name in files:
            with open(self.path(".orchestrator/tmp/handoff/" + name), encoding="utf-8") as f:
                body = f.read()
            self.assertNotIn("hunter2", body)
            self.assertNotIn("abcdef123456", body)

    def test_short(self):
        self.start("s1")
        self.work_in_api()
        for n in range(12):
            self.write("odd/tasks/f%02d.md" % n, TASK)
        self.end("s1")
        text = self.start("s2", at="2026-11-06T12:00:00Z")
        self.assertLessEqual(len(text.split()), 200)

    def test_same_secret_rule_as_memory_check(self):
        with open(os.path.join(SCRIPTS, "memory-check.py"), encoding="utf-8") as f:
            src = f.read()
        rule = re.search(r"SECRET = re\.compile\(\n(.*?)\n\)", src, re.S).group(1)
        with open(os.path.join(SCRIPTS, "session_handoff.py"), encoding="utf-8") as f:
            self.assertIn(rule, f.read())


class Hook(Workspace):
    def hook(self, verb, payload):
        os.makedirs(self.path(".orchestrator/hooks"), exist_ok=True)
        os.makedirs(self.path(".orchestrator/scripts"), exist_ok=True)
        shutil.copy(os.path.join(REPO, "templates", "orchestrator", "hooks", "session-handoff.sh"),
                    self.path(".orchestrator/hooks"))
        for name in ("session_handoff.py", "odd_tasks.py"):
            shutil.copy(os.path.join(SCRIPTS, name), self.path(".orchestrator/scripts"))
        t0 = time.perf_counter()
        p = subprocess.run([BASH, self.path(".orchestrator/hooks/session-handoff.sh"), verb],
                           input=json.dumps(payload).encode(), capture_output=True, timeout=30)
        return p, time.perf_counter() - t0

    def test_start_prints_context_only_when_there_is_a_draft(self):  # O2, O5
        p, _ = self.hook("start", {"session_id": "s1", "hook_event_name": "SessionStart"})
        self.assertEqual((p.returncode, p.stdout), (0, b""))
        self.work_in_api()
        p, elapsed = self.hook("end", {"session_id": "s1", "hook_event_name": "SessionEnd"})
        self.assertEqual((p.returncode, p.stdout), (0, b""))
        print("\nbenchmark S1: end hook %.0f ms" % (elapsed * 1000))
        self.assertLess(elapsed, 2.0)
        p, _ = self.hook("start", {"session_id": "s2", "hook_event_name": "SessionStart"})
        self.assertEqual(p.returncode, 0)
        out = json.loads(p.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        self.assertIn("api: on feat/coupon", out["additionalContext"])

    def test_never_fails_the_session(self):  # O5
        p, _ = self.hook("start", "not an object")
        self.assertEqual((p.returncode, p.stdout), (0, b""))
        os.remove(self.path(".orchestrator/scripts/session_handoff.py"))
        p, _ = self.hook("end", {"session_id": "s1"})
        self.assertEqual((p.returncode, p.stdout), (0, b""))

    def test_no_network_or_model(self):  # O5
        with open(os.path.join(SCRIPTS, "session_handoff.py"), encoding="utf-8") as f:
            src = f.read()
        for word in ("socket", "urllib", "http", "requests", "anthropic", "claude -p", '"gh"'):
            self.assertNotIn(word, src)


if __name__ == "__main__":
    unittest.main()
