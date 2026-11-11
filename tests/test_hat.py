"""Tests for G1: the global hat home, its project registry and `hat resolve` (scripts/hat.py).
  python3 -m unittest tests.test_hat
HAT_HOME points every test at a temporary home; nothing touches ~/.hat.
"""
import hermetic  # noqa: F401  (first: never the real hat home)
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
HAT = os.path.join(REPO, "scripts", "hat.py")


def snapshot(root):
    out = {}
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x != ".git"]
        for name in files:
            with open(os.path.join(d, name), "rb") as f:
                out[os.path.relpath(os.path.join(d, name), root)] = hashlib.sha256(f.read()).hexdigest()
    return out


class Registry(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.work)

    def hat(self, *args, cwd=None):
        p = subprocess.run([sys.executable, HAT] + list(args), capture_output=True, encoding="utf-8",
                           cwd=cwd or self.work, env=dict(os.environ, HAT_HOME=self.home), timeout=30)
        return p.returncode, p.stdout.strip(), p.stderr.strip()

    def folder(self, *parts, git=False):
        path = os.path.join(self.work, *parts)
        os.makedirs(path, exist_ok=True)
        if git:
            subprocess.run(["git", "init", "-q", path], check=True)
        return path

    def test_add_registers_the_project_and_creates_its_state_folder(self):
        root = self.folder("shop")
        code, out, err = self.hat("project", "add", root)
        self.assertEqual(code, 0, err)
        pid = out.split()[0]
        self.assertRegex(pid, r"^shop-[0-9a-f]{6}$")
        self.assertTrue(os.path.isdir(os.path.join(self.home, "projects", pid)))
        with open(os.path.join(self.home, "projects.toml"), encoding="utf-8") as f:
            reg = f.read()
        self.assertIn('[project.%s]' % pid, reg)
        self.assertIn('root = "%s"' % root.replace("\\", "/"), reg)

    def test_two_folders_with_the_same_name_are_two_projects(self):
        a, b = self.folder("a", "shop"), self.folder("b", "shop")
        ids = {self.hat("project", "add", p)[1].split()[0] for p in (a, b)}
        self.assertEqual(len(ids), 2)

    def test_a_root_is_registered_once(self):
        root = self.folder("shop")
        self.hat("project", "add", root)
        code, _, err = self.hat("project", "add", root)
        self.assertEqual(code, 1)
        self.assertIn("already registered", err)

    def test_nested_roots_are_refused(self):
        outer, inner = self.folder("ws"), self.folder("ws", "api")
        self.hat("project", "add", outer)
        code, _, err = self.hat("project", "add", inner)
        self.assertEqual(code, 1)
        self.assertIn("inside", err)
        other = self.folder("other")
        self.hat("project", "add", self.folder("other", "api"))
        code, _, err = self.hat("project", "add", other)
        self.assertEqual(code, 1)
        self.assertIn("contains", err)

    def test_add_without_a_root_takes_the_git_top_level_or_the_folder(self):
        repo = self.folder("single", git=True)
        sub = self.folder("single", "src")
        code, out, err = self.hat("project", "add", cwd=sub)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.hat("resolve", repo)[1].split("\t")[1], repo.replace("\\", "/"))
        multi = self.folder("multi")  # a multi-repo workspace: its parent folder is the root (G-D3)
        self.folder("multi", "api", git=True)
        code, out, err = self.hat("project", "add", cwd=multi)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.hat("resolve", os.path.join(multi, "api"))[1].split("\t")[1],
                         multi.replace("\\", "/"))

    def test_resolve_finds_the_project_from_any_folder_below_it(self):
        root = self.folder("ws")
        deep = self.folder("ws", "api", "src", "x")
        pid = self.hat("project", "add", root)[1].split()[0]
        code, out, _ = self.hat("resolve", deep)
        self.assertEqual(code, 0)
        self.assertEqual(out, "%s\t%s" % (pid, root.replace("\\", "/")))

    def test_resolve_outside_any_project_prints_nothing(self):
        self.hat("project", "add", self.folder("ws"))
        code, out, err = self.hat("resolve", self.folder("elsewhere"))
        self.assertEqual((code, out, err), (1, "", ""))
        self.assertEqual(self.hat("resolve", self.folder("wsx"))[0], 1)  # a prefix of the name is not inside

    def test_resolve_without_a_home_prints_nothing_and_writes_nothing(self):
        code, out, err = self.hat("resolve", self.work)
        self.assertEqual((code, out, err), (1, "", ""))
        self.assertFalse(os.path.exists(self.home))

    def test_move_points_the_project_at_its_new_root(self):
        old = self.folder("ws")
        pid = self.hat("project", "add", old)[1].split()[0]
        new = os.path.join(self.work, "moved")
        os.rename(old, new)
        code, _, err = self.hat("project", "move", pid, new)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.hat("resolve", new)[1], "%s\t%s" % (pid, new.replace("\\", "/")))
        self.assertEqual(self.hat("project", "move", "nope-000000", new)[0], 1)

    def test_list_shows_each_project_and_a_missing_root(self):
        a = self.folder("a")
        self.hat("project", "add", a)
        self.hat("project", "add", self.folder("b"))
        shutil.rmtree(a)
        code, out, _ = self.hat("project", "list")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(any(l.startswith("a-") and "missing" in l for l in lines), out)

    def test_nothing_is_written_inside_the_project(self):
        root = self.folder("ws", git=True)
        with open(os.path.join(root, "README.md"), "w") as f:
            f.write("# ws\n")
        before = snapshot(root)
        pid = self.hat("project", "add", root)[1].split()[0]
        self.hat("resolve", root)
        self.hat("project", "list")
        self.hat("project", "move", pid, root)
        self.assertEqual(snapshot(root), before)

    def test_resolve_is_fast(self):
        for i in range(20):
            self.hat("project", "add", self.folder("p%d" % i))
        start = time.perf_counter()
        self.hat("resolve", self.folder("p7", "deep"))
        self.assertLess(time.perf_counter() - start, 1.0)  # a hook budget; ~50 ms locally, CI runners are slower


if __name__ == "__main__":
    unittest.main()
