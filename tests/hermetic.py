"""Imported first by every test module: the suite never reads or writes the real hat home.
On a machine where this clone is itself a registered hat project, a script run from the clone finds its project
from the folder it runs in (layout.py), so a test would otherwise resolve the real ~/.hat. Every test therefore runs
with HAT_HOME pointing at one empty temporary folder, and without the variables a hat hook sets.
"""
import atexit
import os
import shutil
import tempfile

if not os.environ.get("HAT_TEST_HOME"):
    os.environ["HAT_TEST_HOME"] = tempfile.mkdtemp(prefix="hat-test-home-")
    atexit.register(shutil.rmtree, os.environ["HAT_TEST_HOME"], True)
os.environ["HAT_HOME"] = os.environ["HAT_TEST_HOME"]
for _k in ("HAT_STATE", "HAT_ROOT", "HAT_PROJECT"):
    os.environ.pop(_k, None)
