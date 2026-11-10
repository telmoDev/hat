"""Tests for G3: the global install (scripts/hat_install.py, `bash install.sh --global`). HOME points at a temporary
folder: nothing touches the real ~/.claude, ~/.codex, ~/.agents or ~/.hat.
  python3 -m unittest tests.test_hat_install
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
INSTALL = os.path.join(REPO, "scripts", "hat_install.py")
HOOK = os.path.join(REPO, "scripts", "hat-hook.sh").replace("\\", "/")
EVENTS = ("SessionStart", "SessionEnd", "SubagentStart", "SubagentStop", "PostToolUse", "PostToolUseFailure")


def snapshot(root):
    out = {}
    for d, dirs, files in os.walk(root):
        for name in files:
            with open(os.path.join(d, name), "rb") as f:
                out[os.path.relpath(os.path.join(d, name), root)] = hashlib.sha256(f.read()).hexdigest()
        for name in dirs:
            p = os.path.join(d, name)
            if os.path.islink(p):
                out[os.path.relpath(p, root)] = "link:" + os.readlink(p)
    return out


class Install(unittest.TestCase):
    def setUp(self):
        self.home = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, True)
        self.claude = os.path.join(self.home, ".claude")
        self.env = dict(os.environ, HOME=self.home, USERPROFILE=self.home, HAT_HOME=os.path.join(self.home, ".hat"))

    def run_install(self, *args):
        p = subprocess.run([sys.executable, INSTALL] + list(args), capture_output=True, encoding="utf-8",
                           env=self.env, timeout=60)
        return p.returncode, p.stdout + p.stderr

    def settings(self):
        with open(os.path.join(self.claude, "settings.json"), encoding="utf-8") as f:
            return json.load(f)

    def commands(self, event):
        return [h["command"] for g in self.settings().get("hooks", {}).get(event, []) for h in g["hooks"]]

    def user_setup(self):
        os.makedirs(os.path.join(self.claude, "agents"))
        os.makedirs(os.path.join(self.claude, "skills", "mine"))
        with open(os.path.join(self.claude, "settings.json"), "w") as f:
            json.dump({"model": "opus", "attribution": {"commit": ""},
                       "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
                                                                               "command": "echo mine"}]}]}}, f)
        with open(os.path.join(self.claude, "CLAUDE.md"), "w") as f:
            f.write("# My own notes\n")
        with open(os.path.join(self.claude, "agents", "reviewer.md"), "w") as f:
            f.write("my agent\n")

    def test_install_wires_every_hook_once_through_the_hat_entry(self):
        code, out = self.run_install("install")
        self.assertEqual(code, 0, out)
        for event in EVENTS:
            mine = [c for c in self.commands(event) if HOOK in c]
            self.assertTrue(mine, event)
            self.assertEqual(len(mine), len(set(mine)), event)
        start = " ".join(self.commands("SessionStart"))
        for hook in ("context", "session-memory", "decision-index", "session-handoff\" start", "telemetry\" hook"):
            self.assertIn(hook.replace("\" ", " ").replace('"', ""), start.replace('"', ""))

    def test_agents_skills_and_a_short_pointer(self):
        self.run_install("install")
        for name in ("hat-explorer", "hat-architect", "hat-dev"):
            self.assertTrue(os.path.isfile(os.path.join(self.claude, "agents", name + ".md")))
        # Only the skills the orchestrator invokes are global: every session on the machine lists their
        # descriptions. Standards and the review are read by path from the brief.
        for name in ("design-patterns", "software-principles", "pre-pr-review"):
            self.assertFalse(os.path.lexists(os.path.join(self.claude, "skills", name)), name)
        for name in ("sync-memory", "orchestrator-metrics"):
            for base in (os.path.join(self.claude, "skills"), os.path.join(self.home, ".agents", "skills")):
                link = os.path.join(base, name)
                self.assertTrue(os.path.isfile(os.path.join(link, "SKILL.md")), link)
                self.assertEqual(os.path.realpath(link), os.path.realpath(os.path.join(REPO, "guide", "skills", name)))
        with open(os.path.join(self.claude, "CLAUDE.md"), encoding="utf-8") as f:
            block = f.read()
        self.assertIn("<!-- hat:begin -->", block)
        self.assertLess(len(block.split()), 90)  # every session on the machine loads it

    def test_the_users_setup_is_kept_and_backed_up(self):
        self.user_setup()
        code, out = self.run_install("install")
        self.assertEqual(code, 0, out)
        s = self.settings()
        self.assertEqual((s["model"], s["attribution"]), ("opus", {"commit": ""}))
        self.assertIn("echo mine", self.commands("PreToolUse"))
        self.assertNotIn("autoCompactWindow", s)  # proposed, never set
        self.assertIn("autoCompactWindow", out)
        with open(os.path.join(self.claude, "CLAUDE.md"), encoding="utf-8") as f:
            self.assertTrue(f.read().startswith("# My own notes\n"))
        backups = os.listdir(os.path.join(self.home, ".hat", "backup"))
        self.assertTrue(any(b.startswith("settings.json") for b in backups))

    def test_a_second_install_changes_nothing(self):
        self.user_setup()
        self.run_install("install")
        before = snapshot(self.claude)
        code, out = self.run_install("install")
        self.assertEqual(code, 0, out)
        self.assertEqual(snapshot(self.claude), before)

    def test_uninstall_removes_exactly_what_install_added(self):
        self.user_setup()
        before_settings = json.load(open(os.path.join(self.claude, "settings.json")))
        before = {k: v for k, v in snapshot(self.claude).items() if k != "settings.json"}
        self.run_install("install")
        code, out = self.run_install("uninstall")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.settings(), before_settings)
        self.assertEqual({k: v for k, v in snapshot(self.claude).items() if k != "settings.json"}, before)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".agents", "skills", "sync-memory")))

    def test_it_never_overwrites_what_is_not_its_own(self):
        self.user_setup()
        with open(os.path.join(self.claude, "agents", "hat-dev.md"), "w") as f:
            f.write("someone else's\n")
        os.makedirs(os.path.join(self.claude, "skills", "sync-memory"))
        before = snapshot(self.claude)
        code, out = self.run_install("install")
        self.assertEqual(code, 1)
        self.assertIn("hat-dev.md", out)
        self.assertIn("sync-memory", out)
        self.assertEqual(snapshot(self.claude), before)  # refused before the first write

    def test_a_skill_no_longer_global_is_unlinked_on_the_next_install(self):
        self.run_install("install")
        old = os.path.join(self.claude, "skills", "pre-pr-review")
        os.symlink(os.path.join(REPO, "guide", "skills", "pre-pr-review"), old)
        m = os.path.join(self.home, ".hat", "install.json")
        data = json.load(open(m))
        data["links"].append(old)
        json.dump(data, open(m, "w"))
        self.run_install("install")
        self.assertFalse(os.path.lexists(old))

    def test_check_reports_what_is_missing(self):
        code, out = self.run_install("check")
        self.assertEqual(code, 1)
        self.run_install("install")
        code, out = self.run_install("check")
        self.assertEqual(code, 0, out)

    def test_codex_gets_a_pointer_only_when_it_is_set_up(self):
        self.run_install("install")
        self.assertFalse(os.path.exists(os.path.join(self.home, ".codex")))
        self.run_install("uninstall")
        os.makedirs(os.path.join(self.home, ".codex"))
        self.run_install("install")
        with open(os.path.join(self.home, ".codex", "AGENTS.md"), encoding="utf-8") as f:
            self.assertIn("<!-- hat:begin -->", f.read())

    def test_install_sh_global_runs_it(self):
        p = subprocess.run([shutil.which("bash") or "bash", os.path.join(REPO, "install.sh"), "--global"],
                           capture_output=True, encoding="utf-8", env=self.env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(any(HOOK in c for c in self.commands("SessionStart")))


if __name__ == "__main__":
    unittest.main()
