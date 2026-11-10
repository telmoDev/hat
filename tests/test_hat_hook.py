"""Tests for G2b: the global hook entry (scripts/hat-hook.sh), the session-start header (hat context) and hat's
home as a local git repo (hat commit). HAT_HOME points every test at a temporary home.
  python3 -m unittest tests.test_hat_hook
"""
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
HAT = os.path.join(REPO, "scripts", "hat.py")
HOOK = os.path.join(REPO, "scripts", "hat-hook.sh")
BASH = shutil.which("bash") or "bash"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        self.root = os.path.join(self.tmp, "shop")
        os.makedirs(self.root)
        subprocess.run(["git", "init", "-q", self.root], check=True)
        cfg = os.path.join(self.tmp, "gitconfig")
        with open(cfg, "w") as f:
            f.write("[user]\n\tname = t\n\temail = t@example.com\n[init]\n\tdefaultBranch = main\n"
                    "[commit]\n\tgpgsign = false\n")
        self.env = dict(os.environ, HAT_HOME=self.home, GIT_CONFIG_GLOBAL=cfg, GIT_CONFIG_NOSYSTEM="1")
        for k in ("HAT_STATE", "HAT_ROOT", "HAT_PROJECT", "ORCH_TELEMETRY_DB"):
            self.env.pop(k, None)

    def hat(self, *args, cwd=None, stdin=""):
        p = subprocess.run([sys.executable, HAT] + list(args), input=stdin, capture_output=True, encoding="utf-8",
                           cwd=cwd or self.root, env=self.env, timeout=30)
        return p.returncode, p.stdout, p.stderr

    def add(self):
        code, out, err = self.hat("project", "add", self.root)
        self.assertEqual(code, 0, err)
        self.pid = out.split()[0]
        self.state = os.path.join(self.home, "projects", self.pid)
        return self.pid

    def hook(self, name, payload, *args):
        return subprocess.run([BASH, HOOK, name] + list(args), input=json.dumps(payload), capture_output=True,
                              encoding="utf-8", env=self.env, cwd=self.tmp, timeout=60)

    def git_home(self, *args):
        return subprocess.run(["git", "-C", self.home] + list(args), capture_output=True, encoding="utf-8",
                              env=self.env).stdout


class Hook(Base):
    def start(self, cwd):
        return {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": cwd, "source": "startup",
                "transcript_path": os.path.join(self.tmp, "t.jsonl")}

    def test_in_a_project_the_hook_runs_with_its_state(self):
        self.add()
        p = self.hook("telemetry", self.start(os.path.join(self.root)), "hook", "claude")
        self.assertEqual(p.returncode, 0, p.stderr)
        con = sqlite3.connect(os.path.join(self.state, "telemetry.db"))
        self.assertEqual(con.execute("SELECT project_id FROM runs").fetchall(), [(self.pid,)])
        con.close()

    def test_outside_any_project_nothing_runs_and_nothing_is_written(self):
        self.add()
        elsewhere = os.path.join(self.tmp, "elsewhere")
        os.makedirs(elsewhere)
        p = self.hook("telemetry", self.start(elsewhere), "hook", "claude")
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        self.assertFalse(os.path.exists(os.path.join(self.state, "telemetry.db")))

    def test_without_a_home_the_hook_is_silent(self):
        p = self.hook("session-memory", self.start(self.root))
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))
        self.assertFalse(os.path.exists(self.home))

    def test_a_project_with_its_own_layer_is_left_to_it(self):
        self.add()
        os.makedirs(os.path.join(self.root, ".orchestrator"))
        p = self.hook("telemetry", self.start(self.root), "hook", "claude")
        self.assertEqual(p.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.state, "telemetry.db")))

    def test_bad_input_never_fails_the_session(self):
        self.add()
        p = subprocess.run([BASH, HOOK, "telemetry", "hook", "claude"], input="not json", capture_output=True,
                           encoding="utf-8", env=self.env, timeout=30)
        self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_the_session_start_header_names_the_project_guide_and_rules(self):
        self.add()
        with open(os.path.join(self.state, "config"), "w") as f:
            f.write('REPOS="."\n')
        p = self.hook("context", self.start(os.path.join(self.root)))
        self.assertEqual(p.returncode, 0, p.stderr)
        text = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("hat project %s" % self.pid, text)
        self.assertIn(os.path.join(REPO, "guide", "AGENTS.md").replace("\\", "/"), text)
        self.assertIn(self.state.replace("\\", "/") + "/rules.md", text)
        self.assertLess(len(text), 1500)  # a header, well under the per-hook context limit


class Home(Base):
    def test_the_home_is_a_git_repo_with_a_commit_per_registration(self):
        self.add()
        self.assertIn("add project " + self.pid, self.git_home("log", "--format=%s"))
        ignored = self.git_home("check-ignore", "projects/%s/telemetry.db" % self.pid,
                                "projects/%s/handoff/x.json" % self.pid, "projects/%s/tmp/x" % self.pid)
        self.assertEqual(len(ignored.split()), 3)

    def test_commit_records_the_projects_memory_and_tasks(self):
        self.add()
        os.makedirs(os.path.join(self.state, "memory"))
        with open(os.path.join(self.state, "memory", "NEXT_STEPS.md"), "w") as f:
            f.write("# Next steps\n")
        code, out, err = self.hat("commit", "sync after login", cwd=os.path.join(self.root))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.git_home("log", "-1", "--format=%s"), "%s: sync after login\n" % self.pid)
        self.assertIn("projects/%s/memory/NEXT_STEPS.md" % self.pid, self.git_home("show", "--name-only", "HEAD"))
        code, out, _ = self.hat("commit", "again")
        self.assertEqual(code, 0)
        self.assertIn("nothing to commit", out)

    def test_commit_outside_a_project_is_refused(self):
        self.add()
        elsewhere = os.path.join(self.tmp, "elsewhere")
        os.makedirs(elsewhere)
        code, _, err = self.hat("commit", "x", cwd=elsewhere)
        self.assertEqual(code, 1)
        self.assertIn("not in a hat project", err)


if __name__ == "__main__":
    unittest.main()
