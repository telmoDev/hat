"""The test suite. Run with python3 -m unittest discover -s tests, or one module as tests.test_<name>: either
way tests/ is on the path, so every module can import hermetic first."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
