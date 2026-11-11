"""Tests for per-project git settings a workspace used to fork scripts for (roadmap X4): GH_USER (the gh account a
project's repos need) and PR_TARGETS (the branch a repo's PRs open into, when it isn't the base they branch from).
A real workspace carried both in its own push-pr.sh and memory-state.sh; now they are configuration.
  python3 -m unittest tests.test_pr_targets
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TPL = os.path.join(REPO, "templates", "orchestrator")
BASH = shutil.which("bash") or "bash"
sys.path.insert(0, os.path.join(TPL, "scripts"))
import session_handoff  # noqa: E402  (its SECRET is memory-check's, kept equal by test_session_handoff)

GH = r'''#!/usr/bin/env bash
echo "gh $* | token=${GH_TOKEN:-none}" >> "$GH_LOG"
case "$1 $2" in
  "auth token") echo "tok-$4" ;;
  "pr create") echo https://example.invalid/pr/1 ;;
  "pr list") case " $* " in *" --state all "*) printf 'desarrollo\t5\tmerged\nfeat/old\t6\tmerged\n' ;; esac ;;
esac
'''


class Git(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        cfg = os.path.join(self.tmp, "gitconfig")
        with open(cfg, "w") as f:
            f.write("[user]\n\tname = t\n\temail = t@example.com\n[init]\n\tdefaultBranch = main\n"
                    "[commit]\n\tgpgsign = false\n")
        bin_ = os.path.join(self.tmp, "bin")
        os.makedirs(bin_)
        with open(os.path.join(bin_, "gh"), "w", newline="\n") as f:
            f.write(GH)
        os.chmod(os.path.join(bin_, "gh"), 0o755)
        self.log = os.path.join(self.tmp, "gh.log")
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=cfg, GIT_CONFIG_NOSYSTEM="1", GH_LOG=self.log,
                        PATH=bin_ + os.pathsep + os.environ["PATH"])
        for k in ("HAT_STATE", "HAT_ROOT", "HAT_PROJECT", "GH_TOKEN"):
            self.env.pop(k, None)
        self.ws = os.path.join(self.tmp, "ws")
        self.api = os.path.join(self.ws, "api")
        origin = os.path.join(self.tmp, "origin.git")
        self.git("init", "-q", "--bare", origin)
        self.git("init", "-q", self.api)
        self.git("-C", self.api, "remote", "add", "origin", origin)
        self.commit("chore: init")
        self.git("-C", self.api, "push", "-q", "origin", "main")
        self.git("-C", self.api, "branch", "desarrollo")
        self.git("-C", self.api, "push", "-q", "origin", "desarrollo")
        shutil.copytree(os.path.join(TPL, "scripts"), os.path.join(self.ws, ".orchestrator", "scripts"))
        os.makedirs(os.path.join(self.ws, "memory"))

    def git(self, *args):
        subprocess.run(["git"] + list(args), check=True, capture_output=True, env=self.env)

    def commit(self, msg):
        with open(os.path.join(self.api, "x.txt"), "a") as f:
            f.write(msg + "\n")
        self.git("-C", self.api, "add", "x.txt")
        self.git("-C", self.api, "commit", "-qm", msg)

    def conf(self, extra=""):
        with open(os.path.join(self.ws, ".orchestrator", "orchestrator.conf"), "w") as f:
            f.write('REPOS="api"\nBASE_BRANCHES="api=main"\n' + extra)

    def script(self, name, *args):
        return subprocess.run([BASH, os.path.join(self.ws, ".orchestrator", "scripts", name)] + list(args),
                              capture_output=True, encoding="utf-8", env=self.env, cwd=self.ws, timeout=60)

    def gh_calls(self):
        with open(self.log) as f:
            return f.read()

    def push(self, branch="feat/x"):
        self.git("-C", self.api, "checkout", "-qb", branch, "main")
        self.commit("feat: x")
        p = self.script("pre-pr-pass.sh", "api", branch)
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(os.path.join(self.tmp, "body.md"), "w") as f:
            f.write("Why: a test.\n")
        return self.script("push-pr.sh", "api", branch, "main", "feat: x", os.path.join(self.tmp, "body.md"))

    def test_without_settings_the_pr_opens_into_the_base(self):
        self.conf()
        p = self.push()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("pr create --base main", self.gh_calls())
        self.assertIn("token=none", self.gh_calls())

    def test_pr_targets_opens_the_pr_into_its_branch(self):
        self.conf('PR_TARGETS="api=desarrollo"\n')
        p = self.push()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("pr create --base desarrollo", self.gh_calls())

    def test_the_target_branch_is_never_pushed(self):
        self.conf('PR_TARGETS="api=desarrollo"\n')
        with open(os.path.join(self.tmp, "body.md"), "w") as f:
            f.write("Why.\n")
        p = self.script("push-pr.sh", "api", "desarrollo", "main", "feat: x", os.path.join(self.tmp, "body.md"))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("refusing to push", p.stderr)

    def test_gh_user_runs_gh_as_that_account(self):
        self.conf('GH_USER="bot"\n')
        p = self.push()
        self.assertEqual(p.returncode, 0, p.stderr)
        creates = [l for l in self.gh_calls().splitlines() if l.startswith("gh pr create")]
        self.assertTrue(creates and all(l.endswith("token=tok-bot") for l in creates), self.gh_calls())

    def test_memory_state_keeps_a_long_lived_target_out_of_cleanup(self):
        self.conf('PR_TARGETS="api=desarrollo"\nGH_USER="bot"\n')
        self.git("-C", self.api, "branch", "feat/old", "main")
        with open(os.path.join(self.ws, "memory", "PROJECT_STATE.md"), "w") as f:
            f.write("# Project state\n\nLast sync: 2026-01-01\n"
                    "<!-- state:begin (generated by .orchestrator/scripts/memory-state.sh, do not edit) -->\n"
                    "<!-- state:end -->\n")
        p = self.script("memory-state.sh")
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(os.path.join(self.ws, "memory", "PROJECT_STATE.md")) as f:
            state = f.read()
        self.assertIn("`feat/old`", state)
        self.assertNotIn("`desarrollo`", state.split("## Cleanup")[1])
        self.assertIn("token=tok-bot", self.gh_calls())


class Secret(unittest.TestCase):
    def test_a_long_branch_slug_is_not_a_secret(self):
        self.assertIsNone(session_handoff.SECRET.search("branch soporte-enero-2026-ajustes-reportes-y-exportacion-v2"))

    def test_a_real_token_still_is(self):
        self.assertIsNotNone(session_handoff.SECRET.search("ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0"))
        self.assertIsNotNone(session_handoff.SECRET.search("token: abc123"))


if __name__ == "__main__":
    unittest.main()
