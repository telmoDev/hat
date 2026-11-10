"""Tests for G2: the scripts read and write a project's files in hat's state folder when HAT_STATE is set, run
straight from the clone as the global install runs them, and never write inside the project.
  python3 -m unittest tests.test_layout
"""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TPL = os.path.join(REPO, "templates", "orchestrator")
BASH = shutil.which("bash") or "bash"
sys.path.insert(0, os.path.join(TPL, "scripts"))
import layout  # noqa: E402


def snapshot(root):
    out = {}
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x != ".git"]
        for name in files:
            with open(os.path.join(d, name), "rb") as f:
                out[os.path.relpath(os.path.join(d, name), root)] = hashlib.sha256(f.read()).hexdigest()
    return out


class State(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "shop")
        self.state = os.path.join(self.tmp, "home", "projects", "shop-abc123")
        os.makedirs(os.path.join(self.root, "docs", "adr"))
        subprocess.run(["git", "init", "-q", self.root], check=True)
        with open(os.path.join(self.root, "docs", "adr", "0001-use-postgres.md"), "w") as f:
            f.write("# ADR-0001: Use Postgres\n\n**Status:** Accepted\n")
        for d in ("memory", "tasks"):
            os.makedirs(os.path.join(self.state, d))
        self.write("config", 'REPOS="."\nADR_DIR="docs/adr"\nTEMPLATE_VERSION="0.9.0"\n')
        self.write("memory/NEXT_STEPS.md", "# Next steps\n\n## Resume\n- continue the login\n")
        self.write("memory/PROJECT_STATE.md", "# Project state\n")
        self.before = snapshot(self.root)
        self.env = dict(os.environ, HAT_STATE=self.state, HAT_ROOT=self.root, HAT_PROJECT="shop-abc123")
        self.env.pop("ORCH_TELEMETRY_DB", None)

    def write(self, rel, text):
        with open(os.path.join(self.state, *rel.split("/")), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def run_tpl(self, rel, *args, stdin=""):
        cmd = ([BASH] if rel.endswith(".sh") else [sys.executable]) + [os.path.join(TPL, *rel.split("/"))] + list(args)
        return subprocess.run(cmd, input=stdin, capture_output=True, encoding="utf-8", env=self.env, cwd=self.root,
                              timeout=60)

    def tearDown(self):
        self.assertEqual(snapshot(self.root), self.before, "something was written inside the project")

    def test_layout_points_at_the_state_folder(self):
        old = dict(os.environ)
        try:
            os.environ.update(HAT_STATE=self.state, HAT_ROOT=self.root, HAT_PROJECT="shop-abc123")
            got = layout.of(layout.root(__file__))
        finally:
            os.environ.clear()
            os.environ.update(old)
        self.assertEqual(got.root, self.root)
        self.assertEqual(got.memory, os.path.join(self.state, "memory"))
        self.assertEqual(got.telemetry, os.path.join(self.state, "telemetry.db"))
        self.assertEqual((got.project, got.task_prefix), ("shop-abc123", "tasks/"))

    def test_without_hat_state_nothing_changes(self):
        ws = layout.of("/w")
        self.assertEqual(ws.conf.replace("\\", "/"), "/w/.orchestrator/orchestrator.conf")
        self.assertEqual(ws.tasks.replace("\\", "/"), "/w/odd/tasks")

    def test_telemetry_records_into_the_state_folder(self):
        payload = {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": self.root, "source": "startup",
                   "transcript_path": os.path.join(self.tmp, "t.jsonl")}
        p = self.run_tpl("hooks/telemetry.sh", "hook", "claude", stdin=json.dumps(payload))
        self.assertEqual(p.returncode, 0, p.stderr)
        con = sqlite3.connect(os.path.join(self.state, "telemetry.db"))
        self.assertEqual(con.execute("SELECT run_id, project_id FROM runs").fetchall(), [("claude:s1", "shop-abc123")])
        con.close()

    def test_the_session_handoff_keeps_its_state_there(self):
        payload = json.dumps({"session_id": "s1", "cwd": self.root})
        self.assertEqual(self.run_tpl("hooks/session-handoff.sh", "start", stdin=payload).returncode, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.state, "handoff", "s1.start.json")))
        self.assertEqual(self.run_tpl("hooks/session-handoff.sh", "end", stdin=payload).returncode, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.state, "handoff", "last.json")))

    def test_the_memory_and_decisions_at_start_come_from_the_state_and_the_root(self):
        out = self.run_tpl("hooks/session-memory.sh").stdout
        self.assertIn("continue the login", out)
        self.assertIn("ADR-0001: Use Postgres", self.run_tpl("hooks/decision-index.sh").stdout)

    def test_memory_check_reads_the_state_memory(self):
        self.write("memory/PROGRESS.md", "# Progress\n\ntoken: abc123secret\n")
        p = self.run_tpl("scripts/memory-check.py")
        self.assertIn("PROGRESS.md:3: looks like a secret", p.stdout + p.stderr)

    def test_the_pre_pr_stamp_goes_to_the_state_folder(self):
        git = ["git", "-C", self.root, "-c", "user.name=t", "-c", "user.email=t@e.com"]
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "init"], check=True)
        branch = subprocess.run(["git", "-C", self.root, "branch", "--show-current"], capture_output=True,
                                encoding="utf-8").stdout.strip()
        p = self.run_tpl("scripts/pre-pr-pass.sh", ".", branch)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(os.listdir(os.path.join(self.state, "tmp", "pre-pr")))


if __name__ == "__main__":
    unittest.main()
