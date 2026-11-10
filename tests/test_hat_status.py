"""Tests for G7: `hat status` and `hat doctor`, read-only views across registered projects (scripts/hat.py).
HOME and HAT_HOME point at temporary folders.
  python3 -m unittest tests.test_hat_status
"""
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
        shop, blog = out.split(b)[0], out.split(b)[1]
        self.assertIn(a, shop)
        self.assertIn("finish the cart", shop)
        self.assertIn("cart: T2 the totals", shop)
        self.assertNotIn("old", shop.split("tasks")[1] if "tasks" in shop else "")
        self.assertIn("2026-11-10T10:30:00Z", shop)
        self.assertNotIn("finish the cart", blog)

    def test_status_flags_an_own_layer_and_a_missing_root(self):
        a, ra, _ = self.project("legacy")
        os.makedirs(os.path.join(ra, ".orchestrator"))
        b, rb, _ = self.project("gone")
        shutil.rmtree(rb)
        code, out = self.hat("status")
        self.assertIn("own layer", out.split(a)[1].split(b)[0] if out.index(a) < out.index(b) else out.split(a)[1])
        self.assertIn("root missing", out)

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
        subprocess.run([sys.executable, os.path.join(REPO, "scripts", "hat_install.py"), "install"],
                       capture_output=True, env=self.env, check=True)
        self.project("shop")
        code, out = self.hat("doctor")
        self.assertEqual(code, 0, out)
        self.assertIn("ok", out)


if __name__ == "__main__":
    unittest.main()
