"""Tests for T9: scripts/update.sh on a workspace scaffolded by the real v0.7.0 release, with user changes.
Each test builds a release of the current tree (a local clone tagged v0.8.0) and a v0.7.0 workspace.
  python3 -m unittest discover -s tests
Needs git and bash (Git Bash on Windows), like tests/smoke.sh.
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
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BASH = shutil.which("bash")
sys.path.insert(0, os.path.join(REPO, "templates", "orchestrator", "scripts"))
import telemetry as t  # noqa: E402


def git(*args, cwd=None, env=None):
    return subprocess.run(["git"] + list(args), cwd=cwd, env=env, check=True, capture_output=True).stdout


class Workspace(unittest.TestCase):
    """A v0.7.0 workspace with the user's own changes, and a v0.8.0 release of the current tree."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cfg = os.path.join(cls.tmp, "gitconfig")
        with open(cfg, "w") as f:
            f.write("[user]\n\tname = t\n\temail = t@example.com\n[init]\n\tdefaultBranch = main\n"
                    "[commit]\n\tgpgsign = false\n[core]\n\tautocrlf = false\n")
        cls.env = dict(os.environ, GIT_CONFIG_GLOBAL=cfg, GIT_CONFIG_NOSYSTEM="1")
        # The v0.7.0 release, as an archive of its tag.
        old = os.path.join(cls.tmp, "skill-0.7.0")
        tarfile.open(fileobj=io.BytesIO(git("archive", "v0.7.0", cwd=REPO))).extractall(old)
        cls.old = old
        # A release of the current tree: a clone with the working tree's files, tagged v0.8.0.
        skill = os.path.join(cls.tmp, "skill")
        git("clone", "-q", REPO, skill, env=cls.env)
        for d in ("templates", "scripts"):
            shutil.rmtree(os.path.join(skill, d))
            shutil.copytree(os.path.join(REPO, d), os.path.join(skill, d),
                            ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(os.path.join(REPO, "CHANGELOG.md"), skill)
        with open(os.path.join(skill, "VERSION"), "w") as f:
            f.write("0.8.0\n")
        git("add", "-A", cwd=skill, env=cls.env)
        git("commit", "-qm", "release 0.8.0", "--allow-empty", cwd=skill, env=cls.env)
        git("tag", "v0.8.0", cwd=skill, env=cls.env)
        cls.skill = skill

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.ws = tempfile.mkdtemp(dir=self.tmp)
        api = os.path.join(self.ws, "api")
        os.makedirs(api)
        git("init", "-q", cwd=api, env=self.env)
        with open(os.path.join(api, "README.md"), "w") as f:
            f.write("# api\n")
        git("add", "-A", cwd=api, env=self.env)
        git("commit", "-qm", "init", cwd=api, env=self.env)
        subprocess.run([BASH, os.path.join(self.old, "scripts", "scaffold.sh"), "--git", self.ws.replace("\\", "/")],
                       check=True, capture_output=True, env=self.env)
        # The user's own changes.
        self.edit("memory/NEXT_STEPS.md", lambda s: s.replace("## Pending\n- none", "## Pending\n- my own step"))
        os.makedirs(os.path.join(self.ws, "odd", "tasks"), exist_ok=True)
        with open(os.path.join(self.ws, "odd", "tasks", "login.md"), "w", encoding="utf-8") as f:
            f.write("# login\n\nStatus: active · Next: T1\n")
        self.edit(".orchestrator/orchestrator.conf", lambda s: s.replace("WORD_BUDGET=1200", "WORD_BUDGET=1500"))
        self.edit("AGENTS.md", lambda s: s.replace("- none yet", "- my own rule"))
        self.edit(".orchestrator/scripts/push-pr.sh", lambda s: s + "# my local tweak\n")
        settings = json.loads(self.read(".claude/settings.json"))
        settings["hooks"]["PreToolUse"] = [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo mine"}]}]
        self.write(".claude/settings.json", json.dumps(settings, indent=2) + "\n")
        git("add", "-A", cwd=self.ws, env=self.env)
        git("commit", "-qm", "my workspace", cwd=self.ws, env=self.env)

    # helpers
    def path(self, rel):
        return os.path.join(self.ws, *rel.split("/"))

    def read(self, rel):
        with open(self.path(rel), encoding="utf-8") as f:
            return f.read()

    def write(self, rel, text):
        with open(self.path(rel), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def edit(self, rel, fn):
        self.write(rel, fn(self.read(rel)))

    def template(self, rel):
        with open(os.path.join(self.skill, "templates", *rel.split("/")), encoding="utf-8") as f:
            return f.read()

    def snapshot(self):
        out = {}
        for d, dirs, files in os.walk(self.ws):
            dirs[:] = [x for x in dirs if x != ".git"]
            for name in files:
                p = os.path.join(d, name)
                with open(p, "rb") as f:
                    out[os.path.relpath(p, self.ws)] = hashlib.sha256(f.read()).hexdigest()
        return out

    def update(self, *args, skill=None, env=None):
        p = subprocess.run([BASH, os.path.join(skill or self.skill, "scripts", "update.sh")] + list(args)
                           + [self.ws.replace("\\", "/")], capture_output=True, env=dict(self.env, **(env or {})),
                           timeout=120)
        return p.returncode, p.stdout.decode() + p.stderr.decode()

    def commit(self):
        git("add", "-A", cwd=self.ws, env=self.env)
        git("commit", "-qm", "update", "--allow-empty", cwd=self.ws, env=self.env)


class Update(Workspace):
    def test_keeps_everything_the_user_owns(self):  # F1-14
        before = {r: self.read(r) for r in ("memory/NEXT_STEPS.md", "odd/tasks/login.md", "AGENTS.md")}
        code, out = self.update()
        self.assertEqual(code, 0, out)
        for rel, text in before.items():
            self.assertEqual(self.read(rel), text, rel)
        conf = self.read(".orchestrator/orchestrator.conf")
        self.assertIn("WORD_BUDGET=1500", conf)
        hooks = json.loads(self.read(".claude/settings.json"))["hooks"]
        self.assertEqual(hooks["PreToolUse"][0]["hooks"][0]["command"], "echo mine")

    def test_wires_telemetry_once_and_a_second_run_changes_nothing(self):
        code, out = self.update()
        self.assertEqual(code, 0, out)
        hooks = json.loads(self.read(".claude/settings.json"))["hooks"]
        for event in ("SessionStart", "SessionEnd", "SubagentStart", "SubagentStop", "PostToolUse",
                      "PostToolUseFailure"):
            commands = [h["command"] for g in hooks[event] for h in g["hooks"]]
            self.assertEqual(sum("telemetry.sh" in c for c in commands), 1, event)
        self.assertIn(".orchestrator/telemetry/", self.read(".gitignore").splitlines())
        self.commit()
        before = self.snapshot()
        code, out = self.update()
        self.assertEqual(code, 0, out)
        self.assertIn("No changes", out)
        self.assertEqual(self.snapshot(), before)

    def test_scripts_the_user_changed_are_kept_with_a_new_copy(self):
        code, out = self.update()
        self.assertEqual(code, 0, out)
        self.assertTrue(self.read(".orchestrator/scripts/push-pr.sh").endswith("# my local tweak\n"))
        self.assertEqual(self.read(".orchestrator/scripts/push-pr.sh.new"),
                         self.template("orchestrator/scripts/push-pr.sh"))
        self.assertEqual(self.read(".orchestrator/scripts/memory-check.py"),
                         self.template("orchestrator/scripts/memory-check.py"))  # unchanged by the user: updated
        self.assertIn("Needs your attention", out)
        self.assertIn(".orchestrator/scripts/push-pr.sh.new", out.split("Needs your attention")[1])

    def test_new_files_config_and_version(self):
        code, out = self.update()
        self.assertEqual(code, 0, out)
        for rel in (".orchestrator/scripts/telemetry.py", ".orchestrator/hooks/telemetry.sh", ".orchestrator/rates.json",
                    ".agents/skills/orchestrator-metrics/SKILL.md", ".claude/skills/orchestrator-metrics/SKILL.md"):
            self.assertTrue(os.path.exists(self.path(rel)), rel)
        self.assertNotIn("{{ROOT}}", self.read(".agents/skills/orchestrator-metrics/SKILL.md"))
        conf = self.read(".orchestrator/orchestrator.conf")
        self.assertIn('TELEMETRY="on"', conf)
        self.assertIn('TELEMETRY_TRANSCRIPTS="on"', conf)
        self.assertIn('TEMPLATE_VERSION="0.8.0"', conf)
        self.assertIn("Workspaces", out)  # the manual steps of the CHANGELOG are shown

    def test_telemetry_works_after_the_update(self):
        self.update()
        payload = json.dumps({"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"})
        subprocess.run([BASH, self.path(".orchestrator/hooks/telemetry.sh").replace("\\", "/"), "hook", "claude"],
                       input=payload.encode(), check=True, capture_output=True)
        with sqlite3.connect(self.path(".orchestrator/telemetry/telemetry.db")) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM runs").fetchone()[0], 1)

    def test_an_existing_store_keeps_its_data(self):
        os.makedirs(self.path(".orchestrator/telemetry"))
        db = sqlite3.connect(self.path(".orchestrator/telemetry/telemetry.db"))
        db.executescript("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT);"
                         "INSERT INTO schema_migrations VALUES (1, 'x');" + t.MIGRATIONS[0][1] +
                         "INSERT INTO runs (run_id, starts) VALUES ('claude:old', 1);")
        db.close()
        self.update()
        s = t.Store(self.path(".orchestrator/telemetry/telemetry.db"))
        self.addCleanup(s.close)
        self.assertEqual(s.db.execute("SELECT run_id FROM runs").fetchall(), [("claude:old",)])
        self.assertEqual([r[0] for r in s.db.execute("SELECT version FROM schema_migrations")],
                         [v for v, _ in t.MIGRATIONS])

    def test_dry_run_writes_nothing(self):
        before = self.snapshot()
        code, out = self.update("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("create .orchestrator/scripts/telemetry.py", out)
        self.assertEqual(self.snapshot(), before)

    def test_benchmark_under_5_s_and_idempotent(self):
        start = time.perf_counter()
        code, out = self.update()
        first = time.perf_counter() - start
        self.assertEqual(code, 0, out)
        self.commit()
        before = self.snapshot()
        start = time.perf_counter()
        self.update()
        again = time.perf_counter() - start
        print("\nbenchmark T9: update %.1f s, second run %.1f s (no changes)" % (first, again))
        self.assertEqual(self.snapshot(), before)
        self.assertLess(first, 5)


class Refusals(Workspace):
    def refused(self, *args, want, env=None, skill=None):
        before = self.snapshot()
        code, out = self.update(*args, env=env, skill=skill)
        self.assertNotEqual(code, 0, out)
        self.assertIn(want, out)
        self.assertEqual(self.snapshot(), before)

    def test_uncommitted_changes_in_the_layer(self):
        self.edit("memory/NEXT_STEPS.md", lambda s: s + "- uncommitted\n")
        self.refused(want="uncommitted changes")

    def test_a_workspace_from_before_0_1_0(self):
        shutil.rmtree(self.path(".orchestrator"))
        os.makedirs(self.path(".claude"), exist_ok=True)
        self.write(".claude/orchestrator.conf", 'REPOS="api"\n')
        self.commit()
        self.refused(want="migrate.sh")

    def test_a_version_without_its_tag(self):
        self.edit(".orchestrator/orchestrator.conf", lambda s: s.replace('TEMPLATE_VERSION="0.7.0"',
                                                                         'TEMPLATE_VERSION="0.6.9"'))
        self.commit()
        self.refused(want="v0.6.9")

    def test_a_missing_version(self):
        self.edit(".orchestrator/orchestrator.conf", lambda s: s.replace('TEMPLATE_VERSION="0.7.0"\n', ""))
        self.commit()
        self.refused(want="TEMPLATE_VERSION")

    def test_an_earlier_new_copy_is_never_overwritten(self):
        self.write(".orchestrator/scripts/push-pr.sh.new", "# an older proposal the user hasn't merged\n")
        self.commit()
        self.refused(want="push-pr.sh.new")


class Partial(Workspace):
    def test_a_failure_midway_reports_what_was_done_and_what_is_pending(self):
        code, out = self.update(env={"ORCH_UPDATE_FAIL_AT": ".orchestrator/scripts/reports.py"})
        self.assertNotEqual(code, 0, out)
        self.assertIn("Update incomplete", out)
        done, pending = out.split("Done:")[1].split("Pending:")
        self.assertIn(".orchestrator/scripts/", done)
        self.assertIn(".orchestrator/scripts/reports.py", pending)
        self.assertIn("orchestrator.conf", pending)  # the version is the last step: never bumped on a partial run
        self.assertIn('TEMPLATE_VERSION="0.7.0"', self.read(".orchestrator/orchestrator.conf"))
        self.commit()
        code, out = self.update()
        self.assertEqual(code, 0, out)
        self.assertIn('TEMPLATE_VERSION="0.8.0"', self.read(".orchestrator/orchestrator.conf"))

    def test_an_unreleased_skill_updates_without_claiming_a_version(self):
        code, out = self.update("--dev", skill=REPO)
        self.assertEqual(code, 0, out)
        self.assertIn('TEMPLATE_VERSION="0.7.0"', self.read(".orchestrator/orchestrator.conf"))
        self.assertIn("not a release", out)
        code, out = self.update(skill=REPO)
        self.assertNotEqual(code, 0)
        self.assertIn("--dev", out)


class DevToRelease(Workspace):
    """A workspace updated with --dev from an unreleased skill, then updated without it once the release is out."""

    def dev_skill(self):
        skill = os.path.join(tempfile.mkdtemp(dir=self.tmp), "skill")
        git("clone", "-q", self.skill, skill, env=self.env)
        git("tag", "-d", "v0.8.0", cwd=skill, env=self.env)  # the same tree, before its release
        return skill

    def release(self, skill, *changes):
        for change in changes:
            with open(os.path.join(skill, "templates", "orchestrator", "scripts", change), "a") as f:
                f.write("# changed after the --dev snapshot\n")
        if changes:
            git("commit", "-qam", "a later change", cwd=skill, env=self.env)
        git("tag", "v0.8.0", cwd=skill, env=self.env)

    def test_a_release_equal_to_the_snapshot_needs_no_new_copies(self):
        skill = self.dev_skill()
        code, out = self.update("--dev", skill=skill)
        self.assertEqual(code, 0, out)
        self.assertIn("for testing", out)
        self.commit()
        self.release(skill)
        code, out = self.update(skill=skill)
        self.assertEqual(code, 0, out)
        self.assertIn('TEMPLATE_VERSION="0.8.0"', self.read(".orchestrator/orchestrator.conf"))
        self.assertNotIn("new    ", out)  # nothing kept as changed: the files already are v0.8.0's
        news = [f for d, _, fs in os.walk(self.path(".orchestrator")) for f in fs if f.endswith(".new")]
        self.assertEqual(news, ["push-pr.sh.new"])  # only the user's own change, from the first run

    def test_a_file_the_snapshot_wrote_and_the_release_changed_comes_as_a_new_copy(self):
        skill = self.dev_skill()
        self.update("--dev", skill=skill)
        self.commit()
        self.release(skill, "telemetry.py", "memory-state.sh")
        before = self.read(".orchestrator/scripts/telemetry.py")
        code, out = self.update(skill=skill)
        self.assertEqual(code, 0, out)
        # telemetry.py was written by --dev and changed again: it matches neither v0.7.0 nor v0.8.0, so it is
        # treated as the user's and kept, with the release next to it.
        self.assertEqual(self.read(".orchestrator/scripts/telemetry.py"), before)
        self.assertTrue(self.read(".orchestrator/scripts/telemetry.py.new").endswith(
            "# changed after the --dev snapshot\n"))
        # memory-state.sh was still v0.7.0's (the snapshot didn't change it): updated as usual.
        self.assertTrue(self.read(".orchestrator/scripts/memory-state.sh").endswith(
            "# changed after the --dev snapshot\n"))
        self.assertIn('TEMPLATE_VERSION="0.8.0"', self.read(".orchestrator/orchestrator.conf"))


class Changelog(unittest.TestCase):
    def test_manual_steps_of_every_release_since_the_workspace(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import update
        steps = "\n".join(update.changelog_steps("0.5.1", "0.7.0", True))
        self.assertIn("### v0.7.0", steps)
        self.assertIn("### v0.6.0", steps)
        self.assertNotIn("### v0.5.1", steps)
        self.assertNotIn("### Unreleased", steps)
        self.assertIn("### Unreleased", "\n".join(update.changelog_steps("0.7.0", "0.7.0", False)))


class NewerStore(unittest.TestCase):
    """A store written by a newer orchestrator is never modified nor migrated down."""

    def test_refused_unchanged(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        path = os.path.join(root, "t.db")
        s = t.Store(path)
        s.db.execute("INSERT INTO schema_migrations VALUES (99, 'future')")
        s.close()
        with open(path, "rb") as f:
            before = f.read()
        with self.assertRaises(t.NewerStore) as err:
            t.Store(path)
        self.assertIn("update the orchestrator", str(err.exception))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), before)


if __name__ == "__main__":
    unittest.main()
