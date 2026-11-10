"""Tests for G6a: `hat migrate <workspace>` saves a per-project workspace's own guidelines and state into hat's home,
verbatim, verifies nothing project-specific is missing, and never touches the workspace (scripts/hat_migrate.py).
The workspace is scaffolded by the real v0.7.0 release and adapted the way a user adapts one.
  python3 -m unittest tests.test_hat_migrate
"""
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
HAT = os.path.join(REPO, "scripts", "hat.py")
BASH = shutil.which("bash") or "bash"

RULE = "- Every API change gets a changelog line in docs/api-changes.md."
COMMANDS = "api: `make test` runs the suite; `make test T=<name>` one test; `make lint`."
OWN_PARAGRAPH = "**Our deploys.** Nobody deploys on Fridays; the release train leaves on Tuesdays."


def git(*args, cwd=None, env=None):
    return subprocess.run(["git"] + list(args), cwd=cwd, env=env, capture_output=True, check=True).stdout


def snapshot(root):
    out = {}
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x != ".git"]
        for name in files:
            with open(os.path.join(d, name), "rb") as f:
                out[os.path.relpath(os.path.join(d, name), root)] = hashlib.sha256(f.read()).hexdigest()
    return out


class Migrate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = os.path.realpath(tempfile.mkdtemp())
        cfg = os.path.join(cls.tmp, "gitconfig")
        with open(cfg, "w") as f:
            f.write("[user]\n\tname = t\n\temail = t@example.com\n[init]\n\tdefaultBranch = main\n"
                    "[commit]\n\tgpgsign = false\n[core]\n\tautocrlf = false\n")
        cls.genv = dict(os.environ, GIT_CONFIG_GLOBAL=cfg, GIT_CONFIG_NOSYSTEM="1")
        cls.old = os.path.join(cls.tmp, "skill-0.7.0")
        tarfile.open(fileobj=io.BytesIO(git("archive", "v0.7.0", cwd=REPO))).extractall(cls.old)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.ws = tempfile.mkdtemp(dir=self.tmp)
        self.home = os.path.join(self.ws + "-home", ".hat")
        api = os.path.join(self.ws, "api")
        os.makedirs(api)
        git("init", "-q", cwd=api, env=self.genv)
        with open(os.path.join(api, "README.md"), "w") as f:
            f.write("# api\n")
        git("add", "-A", cwd=api, env=self.genv)
        git("commit", "-qm", "init", cwd=api, env=self.genv)
        subprocess.run([BASH, os.path.join(self.old, "scripts", "scaffold.sh"), "--git", self.ws.replace("\\", "/")],
                       check=True, capture_output=True, env=self.genv)
        self.edit("AGENTS.md", lambda s: s.replace("- none yet", RULE))
        self.edit("AGENTS.md", lambda s: s.replace(
            "TODO(orchestrator-setup): per repo, the commands to run, test (and a single test), lint, format and typecheck.",
            COMMANDS))
        self.edit("AGENTS.md", lambda s: s.replace("## Workspace rules", OWN_PARAGRAPH + "\n\n## Workspace rules"))
        self.edit(".orchestrator/scripts/push-pr.sh", lambda s: s + "# my local tweak\n")
        self.edit("memory/NEXT_STEPS.md", lambda s: s.replace("## Resume\n- none", "## Resume\n- finish the login"))
        os.makedirs(os.path.join(self.ws, "odd", "tasks"), exist_ok=True)
        with open(os.path.join(self.ws, "odd", "tasks", "login.md"), "w", encoding="utf-8") as f:
            f.write("# login\n\nStatus: active · Next: T2\n")
        tel = os.path.join(self.ws, ".orchestrator", "telemetry")
        os.makedirs(tel)
        con = sqlite3.connect(os.path.join(tel, "telemetry.db"))
        con.execute("CREATE TABLE runs (run_id TEXT, started_at TEXT, finished_at TEXT)")
        con.execute("INSERT INTO runs VALUES ('claude:s1', '2026-11-01T10:00:00Z', '2026-11-01T11:00:00Z')")
        con.commit()
        con.close()
        git("add", "-A", cwd=self.ws, env=self.genv)
        git("commit", "-qm", "my workspace", cwd=self.ws, env=self.genv)
        self.env = dict(self.genv, HAT_HOME=self.home)
        for k in ("HAT_STATE", "HAT_ROOT", "HAT_PROJECT"):
            self.env.pop(k, None)
        self.before = snapshot(self.ws)

    def tearDown(self):
        self.assertEqual(snapshot(self.ws), self.before, "migrate changed the workspace")
        shutil.rmtree(self.ws + "-home", ignore_errors=True)

    def edit(self, rel, fn):
        p = os.path.join(self.ws, *rel.split("/"))
        with open(p, encoding="utf-8") as f:
            text = f.read()
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(fn(text))

    def migrate(self, *args):
        p = subprocess.run([sys.executable, HAT, "migrate", self.ws] + list(args), capture_output=True,
                           encoding="utf-8", env=self.env, timeout=120)
        return p.returncode, p.stdout + p.stderr

    def state(self):
        with open(os.path.join(self.home, "projects.toml"), encoding="utf-8") as f:
            pid = f.read().split("[project.")[1].split("]")[0]
        return os.path.join(self.home, "projects", pid)

    def read_state(self, rel):
        with open(os.path.join(self.state(), *rel.split("/")), encoding="utf-8") as f:
            return f.read()

    def test_dry_run_writes_nothing(self):
        code, out = self.migrate("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("rules.md", out)
        self.assertFalse(os.path.exists(self.home))

    def test_the_projects_state_is_copied_as_it_is(self):
        code, out = self.migrate()
        self.assertEqual(code, 0, out)
        for rel, state_rel in (("memory/NEXT_STEPS.md", "memory/NEXT_STEPS.md"), ("odd/tasks/login.md", "tasks/login.md"),
                               (".orchestrator/orchestrator.conf", "config")):
            with open(os.path.join(self.ws, *rel.split("/")), encoding="utf-8") as f:
                self.assertEqual(self.read_state(state_rel), f.read(), rel)
        con = sqlite3.connect(os.path.join(self.state(), "telemetry.db"))
        self.assertEqual(con.execute("SELECT run_id FROM runs").fetchall(), [("claude:s1",)])
        con.close()

    def test_the_projects_own_guidelines_are_saved_verbatim(self):
        self.migrate()
        rules = self.read_state("rules.md")
        for text in (RULE, COMMANDS, OWN_PARAGRAPH):
            self.assertIn(text, rules)
        self.assertNotIn("**Ask or change.**", rules)  # the template's own text is hat's, not the project's
        with open(os.path.join(self.state(), "overrides", ".orchestrator", "scripts", "push-pr.sh"), encoding="utf-8") as f:
            self.assertTrue(f.read().endswith("# my local tweak\n"))
        self.assertFalse(os.path.exists(os.path.join(self.state(), "overrides", ".orchestrator", "scripts",
                                                     "memory-check.py")))  # unchanged: hat's

    def test_the_whole_layer_is_kept_and_the_report_says_what_to_review(self):
        code, out = self.migrate()
        layer = os.path.join(self.state(), "migrated-layer")
        for rel in ("AGENTS.md", "CLAUDE.md", ".orchestrator/orchestrator.conf", "memory/NEXT_STEPS.md"):
            self.assertTrue(os.path.isfile(os.path.join(layer, *rel.split("/"))), rel)
        self.assertIn("verified", out)
        self.assertIn("review", out)
        with open(os.path.join(self.state(), "migrated.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["from"], self.ws.replace("\\", "/"))

    def test_refusals(self):
        self.edit("memory/NEXT_STEPS.md", lambda s: s + "\n- uncommitted\n")
        code, out = self.migrate()
        self.assertEqual(code, 1)
        self.assertIn("uncommitted", out)
        git("checkout", "--", "memory/NEXT_STEPS.md", cwd=self.ws, env=self.genv)
        self.assertEqual(self.migrate()[0], 0)
        code, out = self.migrate()
        self.assertEqual(code, 1)
        self.assertIn("already migrated", out)
        p = subprocess.run([sys.executable, HAT, "migrate", os.path.join(self.ws, "api")], capture_output=True,
                           encoding="utf-8", env=self.env)
        self.assertEqual(p.returncode, 1)
        self.assertIn("not a workspace", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
