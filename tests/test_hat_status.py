"""Tests for G7: `hat status` and `hat doctor`, read-only views across registered projects (scripts/hat.py).
HOME and HAT_HOME point at temporary folders.
  python3 -m unittest tests.test_hat_status
"""
import hermetic  # noqa: F401  (first: never the real hat home)
import hashlib
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


def snapshot(*roots):
    out = {}
    for root in roots:
        for d, dirs, files in os.walk(root):
            for name in files:
                p = os.path.join(d, name)
                with open(p, "rb") as f:
                    out[p] = hashlib.sha256(f.read()).hexdigest()
    return out


def block(out, pid):
    """The lines of one project in `hat status`: from its id to the next project's."""
    lines = out.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(pid + " "))
    end = next((i for i in range(start + 1, len(lines)) if not lines[i].startswith(" ")), len(lines))
    return "\n".join(lines[start:end])


class Views(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home", ".hat")
        cfg = os.path.join(self.tmp, "gitconfig")
        with open(cfg, "w") as f:
            f.write("[user]\n\tname = t\n\temail = t@example.com\n[init]\n\tdefaultBranch = main\n")
        self.env = dict(os.environ, HOME=os.path.join(self.tmp, "home"), USERPROFILE=os.path.join(self.tmp, "home"),
                        HAT_HOME=self.home, GIT_CONFIG_GLOBAL=cfg, GIT_CONFIG_NOSYSTEM="1")
        for k in ("HAT_STATE", "HAT_ROOT", "HAT_PROJECT"):
            self.env.pop(k, None)

    def hat(self, *args):
        p = subprocess.run([sys.executable, HAT] + list(args), capture_output=True, encoding="utf-8",
                           env=self.env, cwd=self.tmp, timeout=60)
        return p.returncode, p.stdout + p.stderr

    def project(self, name):
        root = os.path.join(self.tmp, name)
        os.makedirs(root)
        code, out = self.hat("project", "add", root)
        pid = out.split()[0]
        return pid, root, os.path.join(self.home, "projects", pid)

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_status_shows_each_project_apart(self):
        a, ra, sa = self.project("shop")
        b, rb, sb = self.project("blog")
        self.write(os.path.join(sa, "memory", "NEXT_STEPS.md"), "# Next steps\n\n## Resume\n- finish the cart\n\n## Pending\n- none\n")
        self.write(os.path.join(sa, "tasks", "cart.md"), "# cart\n\nStatus: active · Next: T2 the totals\n")
        self.write(os.path.join(sa, "tasks", "old.md"), "# old\n\nStatus: done · Next: —\n")
        con = sqlite3.connect(os.path.join(sa, "telemetry.db"))
        con.execute("CREATE TABLE runs (run_id TEXT, started_at TEXT, finished_at TEXT)")
        con.execute("INSERT INTO runs VALUES ('claude:s1', '2026-11-10T10:00:00Z', '2026-11-10T10:30:00Z')")
        con.commit()
        con.close()
        code, out = self.hat("status")
        self.assertEqual(code, 0, out)
        shop, blog = block(out, a), block(out, b)
        self.assertIn("finish the cart", shop)
        self.assertIn("1 active · cart: T2 the totals", shop)
        self.assertIn("2026-11-10T10:30:00Z", shop)
        self.assertNotIn("finish the cart", blog)
        self.assertIn("none active", blog)

    def test_status_flags_an_own_layer_and_a_missing_root(self):
        a, ra, _ = self.project("legacy")
        os.makedirs(os.path.join(ra, ".orchestrator"))
        b, rb, _ = self.project("gone")
        shutil.rmtree(rb)
        code, out = self.hat("status")
        self.assertIn("own layer", block(out, a))
        self.assertIn("root missing", block(out, b))

    def test_status_says_when_a_migrated_workspace_awaits_its_cleanup(self):
        a, ra, sa = self.project("legacy")
        os.makedirs(os.path.join(ra, ".orchestrator"))
        self.write(os.path.join(sa, "migrated.json"), "{}")
        code, out = self.hat("status")
        self.assertIn("migrated", block(out, a))
        self.assertIn("--cleanup", block(out, a))

    def test_status_reads_only(self):
        a, ra, sa = self.project("shop")
        self.write(os.path.join(sa, "memory", "NEXT_STEPS.md"), "# Next\n")
        before = snapshot(self.home, ra)
        self.hat("status")
        self.hat("doctor")
        self.assertEqual(snapshot(self.home, ra), before)

    def test_status_with_no_projects(self):
        code, out = self.hat("status")
        self.assertEqual(code, 0)
        self.assertIn("no projects", out)
        self.assertFalse(os.path.exists(self.home))

    def test_doctor_reports_a_missing_install_and_a_missing_root(self):
        _, root, _ = self.project("gone")
        shutil.rmtree(root)
        code, out = self.hat("doctor")
        self.assertEqual(code, 1)
        self.assertIn("global install", out)
        self.assertIn("root missing", out)

    def test_doctor_is_happy_after_the_install(self):
        # A stand-in claude on PATH: CI runners have none, and doctor rightly reports that.
        bin_ = os.path.join(self.tmp, "bin")
        os.makedirs(bin_)
        stub = os.path.join(bin_, "claude.py" if os.name == "nt" else "claude")
        with open(stub, "w", newline="\n") as f:
            f.write("#!%s\nprint('9.9.9 (Claude Code)')\n" % sys.executable)
        os.chmod(stub, 0o755)
        if os.name == "nt":
            with open(os.path.join(bin_, "claude.cmd"), "w") as f:
                f.write('@"%s" "%s" %%*\n' % (sys.executable, stub))
        self.env["PATH"] = bin_ + os.pathsep + self.env.get("PATH", "")
        subprocess.run([sys.executable, os.path.join(REPO, "scripts", "hat_install.py"), "install"],
                       capture_output=True, env=self.env, check=True)
        self.project("shop")
        code, out = self.hat("doctor")
        self.assertEqual(code, 0, out)
        self.assertIn("ok", out)


if __name__ == "__main__":
    unittest.main()
