"""Unit tests for odd_tasks.py, the task-file parser memory-check.py and telemetry.py share.
  python3 -m unittest discover -s tests
"""
import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "templates", "orchestrator", "scripts")
sys.path.insert(0, SCRIPTS)
import odd_tasks as ot  # noqa: E402

TASK_FILE = """# login

Status: active · Next: T2 the form
Ticket: — · Repos: api · PRs: —

## Request
> make login work

## Outcome
Goal: users log in
Outcome: a session after a valid password
Criteria: O1 a valid password opens a session · O2 a wrong one is refused · O3 the form shows the error
Constraints: none

## Tasks
| ID | Task | Serves | Depends on | Agent · tier | Status |
|---|---|---|---|---|---|
| T1 | login endpoint | S1 · O1 O2 | — | api-dev · normal | done |
| T2 | login form | S2 · O3 | T1 | web-dev · normal | blocked (waits on the design) |
| T3 | docs | — | T1 | api-dev · trivial | in progress |

## Evidence
- 2026-11-01 T1 · O1 · `pytest tests/test_login.py::test_valid` → failed: AssertionError
- 2026-11-02 T1 · O1 · `pytest tests/test_login.py::test_valid` → passed: 1 passed
- 2026-11-02 T1 · O2 · `pytest tests/test_login.py::test_wrong` → passed: 1 passed
- 2026-11-02 T3 · TDD skipped: docs only · checked with `mkdocs build`

```
- 2026-11-03 T2 · O3 · `this is an example in a code block` → passed: ignored
```

## Run log
- 2026-11-02 T1 · api-dev · normal · attempt 1 · tokens not reported · duration not reported · done · —
"""


class Parser(unittest.TestCase):
    def test_task_state_keeps_memory_check_behaviour(self):
        self.assertEqual(ot.task_state(TASK_FILE), {
            "status": "active",
            "tasks": [("T1", "done"), ("T2", "blocked (waits on the design)"), ("T3", "in progress")],
            "evidence": {"T1", "T3"},
            "passed": 2,
            "total": 3,
        })

    def test_evidence_entries_in_file_order(self):
        self.assertEqual(ot.evidence(TASK_FILE), [
            {"date": "2026-11-01", "tasks": ["T1"], "criteria": ["O1"], "result": "failed", "method": "command"},
            {"date": "2026-11-02", "tasks": ["T1"], "criteria": ["O1"], "result": "passed", "method": "command"},
            {"date": "2026-11-02", "tasks": ["T1"], "criteria": ["O2"], "result": "passed", "method": "command"},
        ])

    def test_task_rows(self):
        self.assertEqual(ot.task_rows(TASK_FILE), [
            ("T1", "login endpoint", "done"),
            ("T2", "login form", "blocked (waits on the design)"),
            ("T3", "docs", "in progress"),
        ])

    def test_pure_module(self):
        with open(os.path.join(SCRIPTS, "odd_tasks.py")) as f:
            tree = ast.parse(f.read())
        names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        names |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(names, {"re"})  # no I/O, no paths: callers read the files
        top = [type(n).__name__ for n in tree.body]
        self.assertTrue(set(top) <= {"Expr", "Import", "Assign", "FunctionDef"}, top)


if __name__ == "__main__":
    unittest.main()
