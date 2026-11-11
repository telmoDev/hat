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


class Workspace(unittest.TestCase):
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



class Migrate(Workspace):
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

    def test_files_a_later_hat_brought_are_hats(self):
        # update.sh --dev leaves TEMPLATE_VERSION at 0.7.0 but brings today's scripts: they are hat's, not the project's.
        p = subprocess.run([BASH, os.path.join(REPO, "scripts", "update.sh"), "--dev", self.ws.replace("\\", "/")],
                           capture_output=True, encoding="utf-8", env=self.genv)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        git("add", "-A", cwd=self.ws, env=self.genv)
        git("commit", "-qm", "update", cwd=self.ws, env=self.genv)
        self.before = snapshot(self.ws)
        code, out = self.migrate()
        self.assertEqual(code, 0, out)
        overrides = os.path.join(self.state(), "overrides")
        found = sorted(os.path.relpath(os.path.join(d, f), overrides).replace("\\", "/")
                       for d, _, fs in os.walk(overrides) for f in fs)
        self.assertIn(".orchestrator/scripts/push-pr.sh", found)  # the user's own tweak
        for hats in (".orchestrator/scripts/telemetry.py", ".orchestrator/scripts/layout.py",
                     ".claude/skills/sync-memory/SKILL.md", ".orchestrator/update-keep"):
            self.assertNotIn(hats, found)

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


class Cleanup(Workspace):
    """--cleanup, after a verified migration: one commit removes hat's layer files and nothing else."""

    def tearDown(self):
        shutil.rmtree(self.ws + "-home", ignore_errors=True)

    def hook(self, name, cwd):
        return subprocess.run([BASH, os.path.join(REPO, "scripts", "hat-hook.sh"), name],
                              input=json.dumps({"cwd": cwd, "session_id": "s1"}), capture_output=True,
                              encoding="utf-8", env=self.env, timeout=60)

    def own_extras(self):
        # The user's own skill and settings, which cleanup must keep.
        os.makedirs(os.path.join(self.ws, ".agents", "skills", "tickets"))
        with open(os.path.join(self.ws, ".agents", "skills", "tickets", "SKILL.md"), "w") as f:
            f.write("---\nname: tickets\n---\nmine\n")
        p = os.path.join(self.ws, ".claude", "settings.json")
        s = json.load(open(p))
        s.setdefault("permissions", {})["allow"] = ["Bash(make test)"]
        json.dump(s, open(p, "w"), indent=2)
        git("add", "-A", cwd=self.ws, env=self.genv)
        git("commit", "-qm", "extras", cwd=self.ws, env=self.genv)

    def test_cleanup_needs_a_migration(self):
        code, out = self.migrate("--cleanup")
        self.assertEqual(code, 1)
        self.assertIn("not migrated", out)

    def test_cleanup_refuses_when_the_layer_changed_since(self):
        self.migrate()
        self.edit("memory/NEXT_STEPS.md", lambda s: s + "\n- later\n")
        git("commit", "-qam", "later", cwd=self.ws, env=self.genv)
        code, out = self.migrate("--cleanup")
        self.assertEqual(code, 1)
        self.assertIn("changed since", out)
        self.assertTrue(os.path.isdir(os.path.join(self.ws, ".orchestrator")))

    def test_cleanup_removes_only_hats_files_in_one_commit(self):
        self.own_extras()
        api_before = snapshot(os.path.join(self.ws, "api"))
        self.assertEqual(self.migrate()[0], 0)
        code, out = self.migrate("--cleanup")
        self.assertEqual(code, 0, out)
        for gone in ("AGENTS.md", "CLAUDE.md", ".orchestrator", "memory", "odd", ".agents/skills/sync-memory",
                     ".claude/skills/sync-memory", ".claude/workflows", ".claude/agents/explorer.md"):
            self.assertFalse(os.path.exists(os.path.join(self.ws, *gone.split("/"))), gone)
        self.assertTrue(os.path.isfile(os.path.join(self.ws, ".agents", "skills", "tickets", "SKILL.md")))
        s = json.load(open(os.path.join(self.ws, ".claude", "settings.json")))
        self.assertEqual(s["permissions"]["allow"], ["Bash(make test)"])
        self.assertNotIn(".orchestrator/", json.dumps(s.get("hooks", {})))
        self.assertEqual(snapshot(os.path.join(self.ws, "api")), api_before)  # the app repo is never touched
        log = git("log", "--format=%s", cwd=self.ws, env=self.genv).decode()
        self.assertTrue(log.startswith("chore: move the orchestration layer to hat"), log)
        self.assertEqual(git("status", "--porcelain", cwd=self.ws, env=self.genv), b"")
        header = self.hook("context", self.ws).stdout  # the project now runs on hat
        self.assertIn("hat project", header)

    def test_session_start_offers(self):
        self.assertIn("hat.py migrate", self.hook("context", self.ws).stdout)  # an old layer, not registered
        self.migrate()
        self.assertIn("--cleanup", self.hook("context", self.ws).stdout)  # migrated, old layer still there
        plain = os.path.join(self.ws + "-home", "plain")
        os.makedirs(plain)
        self.assertEqual(self.hook("context", plain).stdout, "")  # not a git repo: nothing
        git("init", "-q", plain, env=self.genv)
        self.assertIn("project add", self.hook("context", plain).stdout)  # an unregistered repo (G-D1)


class Refresh(Workspace):
    """--refresh: a workspace still in use between its migration and its cleanup."""

    def tearDown(self):
        shutil.rmtree(self.ws + "-home", ignore_errors=True)

    def test_a_git_wrapper_inside_the_layer_moves_to_the_state(self):
        os.makedirs(os.path.join(self.ws, ".orchestrator", "scripts"), exist_ok=True)
        with open(os.path.join(self.ws, ".orchestrator", "scripts", "gh-git.sh"), "w", newline="\n") as f:
            f.write("#!/usr/bin/env bash\nrepo=$1; shift; exec git -C \"$repo\" \"$@\"\n")
        self.edit(".orchestrator/orchestrator.conf",
                  lambda s: s.replace('GIT_WRAPPER=""', 'GIT_WRAPPER=".orchestrator/scripts/gh-git.sh"'))
        git("add", "-A", cwd=self.ws, env=self.genv)
        git("commit", "-qm", "wrapper", cwd=self.ws, env=self.genv)
        self.assertEqual(self.migrate()[0], 0)
        moved = os.path.join(self.state(), "bin", "gh-git.sh")
        self.assertTrue(os.path.isfile(moved))
        self.assertIn('GIT_WRAPPER="%s"' % moved.replace("\\", "/"), self.read_state("config"))

    def test_refresh_needs_a_migration(self):
        code, out = self.migrate("--refresh")
        self.assertEqual(code, 1)
        self.assertIn("not migrated", out)

    def test_refresh_brings_the_new_state_and_keeps_the_review(self):
        self.assertEqual(self.migrate()[0], 0)
        with open(os.path.join(self.state(), "rules.md"), "a", encoding="utf-8") as f:
            f.write("\n- Reviewed with the user.\n")
        with open(os.path.join(self.state(), "config"), "a", encoding="utf-8") as f:
            f.write('TICKETS="github"\n')
        self.edit("memory/NEXT_STEPS.md", lambda s: s + "\n- after the migration\n")
        with open(os.path.join(self.ws, "odd", "tasks", "cart.md"), "w", encoding="utf-8") as f:
            f.write("# cart\n\nStatus: active · Next: T1\n")
        new_rule = "- Deploys need a second reviewer."
        self.edit("AGENTS.md", lambda s: s.replace(RULE, RULE + "\n" + new_rule))
        git("add", "-A", cwd=self.ws, env=self.genv)
        git("commit", "-qm", "work after the migration", cwd=self.ws, env=self.genv)
        self.assertEqual(self.migrate("--cleanup")[0], 1)  # out of date: refused
        code, out = self.migrate("--refresh")
        self.assertEqual(code, 0, out)
        self.assertIn("after the migration", self.read_state("memory/NEXT_STEPS.md"))
        self.assertTrue(os.path.isfile(os.path.join(self.state(), "tasks", "cart.md")))
        rules = self.read_state("rules.md")
        self.assertIn("- Reviewed with the user.", rules)  # the review is kept
        self.assertIn(new_rule, rules.split("## Added since the migration")[1])
        self.assertIn('TICKETS="github"', self.read_state("config"))  # the state's config is kept
        self.assertEqual(self.migrate("--cleanup")[0], 0)


if __name__ == "__main__":
    unittest.main()
