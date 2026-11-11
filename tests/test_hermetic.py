"""The suite is hermetic: every test module imports tests/hermetic.py first, so no test reads or writes the real
hat home, even on a machine where this clone is a registered hat project.
  python3 -m unittest tests.test_hermetic
"""
import hermetic  # noqa: F401  (first: never the real hat home)
import glob
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class Hermetic(unittest.TestCase):
    def test_every_test_module_imports_hermetic_first(self):
        for path in sorted(glob.glob(os.path.join(HERE, "test_*.py"))):
            with open(path, encoding="utf-8") as f:
                body = re.sub(r'(?s)^""".*?"""\n', "", f.read(), count=1)
            first = next(l for l in body.splitlines() if l.strip() and not l.startswith("#"))
            self.assertTrue(first.startswith("import hermetic"), "%s: %s" % (os.path.basename(path), first))

    def test_the_home_is_a_temporary_folder(self):
        self.assertEqual(os.environ["HAT_HOME"], os.environ["HAT_TEST_HOME"])
        self.assertNotEqual(os.path.realpath(os.environ["HAT_HOME"]),
                            os.path.realpath(os.path.join(os.path.expanduser("~"), ".hat")))
        for k in ("HAT_STATE", "HAT_ROOT", "HAT_PROJECT"):
            self.assertNotIn(k, os.environ)


if __name__ == "__main__":
    unittest.main()
