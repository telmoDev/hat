"""Tests for G8: compaction that loses nothing. PreCompact saves where the session is; the SessionStart that follows
(source "compact") shows it once; telemetry records each compaction with the context size before it.
Payload shapes checked live on Claude Code 2.1.311 (2026-11-10): PreCompact carries trigger, custom_instructions,
session_id, cwd, transcript_path, prompt_id; the next SessionStart has source "compact" and the same session_id.
  python3 -m unittest tests.test_compaction
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SCRIPTS = os.path.join(REPO, "templates", "orchestrator", "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import claude_transcript  # noqa: E402
import session_handoff  # noqa: E402
import telemetry  # noqa: E402
import hat_install  # noqa: E402


def assistant(mid, inp, read, write, out=10):
    return json.dumps({"type": "assistant", "requestId": mid, "message": {
        "id": mid, "model": "claude-opus-5-5", "usage": {"input_tokens": inp, "output_tokens": out,
                                                         "cache_read_input_tokens": read,
                                                         "cache_creation_input_tokens": write}}})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.transcript = os.path.join(self.tmp, "t.jsonl")
        with open(self.transcript, "w") as f:
            f.write(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n")
            f.write(assistant("r1", 100, 1000, 50) + "\n")
            f.write(assistant("r2", 20, 90000, 3000) + "\n")

    def pre_compact(self, transcript=None):
        return {"hook_event_name": "PreCompact", "session_id": "s1", "cwd": self.tmp, "trigger": "manual",
                "custom_instructions": "", "prompt_id": "p1", "transcript_path": transcript or self.transcript}


class Telemetry(Base):
    def test_the_context_size_is_the_last_requests_input(self):
        self.assertEqual(claude_transcript.context_tokens(self.transcript), (93020, None))
        self.assertEqual(claude_transcript.context_tokens(os.path.join(self.tmp, "none.jsonl"))[0], None)

    def test_a_compaction_is_an_event_with_its_trigger_and_context(self):
        events = telemetry.claude_events(self.pre_compact(), {}, "shop")
        self.assertEqual([e["event_type"] for e in events], ["session.compacted"])
        self.assertEqual(events[0]["payload"], {"trigger": "manual", "context_tokens": 93020,
                                                "source": "runtime_reported"})

    def test_an_unreadable_transcript_says_so(self):
        e = telemetry.claude_events(self.pre_compact(os.path.join(self.tmp, "none.jsonl")), {}, "shop")[0]
        self.assertEqual((e["payload"]["source"], "context_tokens" in e["payload"]), ("unavailable", False))

    def test_the_run_report_counts_compactions(self):
        db = os.path.join(self.tmp, "telemetry.db")
        store = telemetry.Store(db)
        try:
            start = {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup",
                     "transcript_path": self.transcript}
            for p in (start, self.pre_compact(), dict(start, source="compact")):
                for e in telemetry.claude_events(p, {}, "shop"):
                    store.record(e)
        finally:
            store.close()
        out = subprocess.run([sys.executable, os.path.join(SCRIPTS, "telemetry.py"), "report", "claude:s1"],
                             capture_output=True, encoding="utf-8", env=dict(os.environ, ORCH_TELEMETRY_DB=db)).stdout
        self.assertIn("Compactions 1 (manual 1) · context before: 93,020 tokens", out)


class Handoff(Base):
    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.tmp, "shop")
        os.makedirs(self.root)
        subprocess.run(["git", "init", "-q", self.root], check=True)
        self.state = os.path.join(self.tmp, "state")
        os.makedirs(os.path.join(self.state, "tasks"))
        os.makedirs(os.path.join(self.state, "memory"))
        with open(os.path.join(self.state, "tasks", "cart.md"), "w") as f:
            f.write("# cart\n\nStatus: active · Next: T2 the totals\n")
        with open(os.path.join(self.state, "config"), "w") as f:
            f.write('REPOS="."\n')
        env = {"HAT_STATE": self.state, "HAT_ROOT": self.root, "HAT_PROJECT": "shop-abc123"}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_compaction_leaves_a_draft_shown_once_after_it(self):
        session_handoff.start(self.root, {"session_id": "s1", "source": "startup"})
        session_handoff.compact(self.root, self.pre_compact())
        text = session_handoff.start(self.root, {"session_id": "s1", "source": "compact"})
        self.assertIn("compacted", text)
        self.assertIn("cart", text)
        self.assertIsNone(session_handoff.start(self.root, {"session_id": "s1", "source": "compact"}))

    def test_saved_even_when_the_memory_is_synced(self):
        session_handoff.start(self.root, {"session_id": "s1", "source": "startup"})
        with open(os.path.join(self.state, "memory", "NEXT_STEPS.md"), "w") as f:
            f.write("# synced\n")
        session_handoff.compact(self.root, self.pre_compact())
        self.assertIn("cart", session_handoff.start(self.root, {"session_id": "s1", "source": "compact"}) or "")

    def test_another_sessions_start_does_not_take_it(self):
        session_handoff.compact(self.root, self.pre_compact())
        self.assertIsNone(session_handoff.start(self.root, {"session_id": "s2", "source": "startup"}))


class Wiring(unittest.TestCase):
    def test_the_global_install_wires_pre_compact(self):
        pre = [(h, a) for e, _, h, a, _ in hat_install.HOOKS if e == "PreCompact"]
        self.assertIn(("session-handoff", "compact"), pre)
        self.assertIn(("telemetry", "hook claude"), pre)

    def test_the_per_project_settings_wire_it_too(self):
        with open(os.path.join(REPO, "templates", "claude", "settings.json"), encoding="utf-8") as f:
            cmds = " ".join(h["command"] for g in json.load(f)["hooks"].get("PreCompact", []) for h in g["hooks"])
        self.assertIn("session-handoff.sh\" compact", cmds)
        self.assertIn("telemetry.sh\" hook claude", cmds)


if __name__ == "__main__":
    unittest.main()
