"""Unit tests for the Claude Code side of the telemetry: hook payloads to contract events, and the transcript
parser. Payload shapes follow the hooks reference (code.claude.com/docs/en/hooks) and Claude Code 2.1.308 as
observed; transcript lines keep only the keys the parser reads, with the shape real transcripts have.
  python3 -m unittest discover -s tests
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(os.path.dirname(HERE), "templates", "orchestrator")
sys.path.insert(0, os.path.join(TPL, "scripts"))
import claude_transcript as ct  # noqa: E402
import telemetry as t  # noqa: E402

BASH = shutil.which("bash")


def line(mid, model="claude-sonnet-5-5", inp=3, out=100, cread=1000, cwrite=50, **extra):
    msg = {"id": mid, "model": model, "role": "assistant", "content": [{"type": "text", "text": "SECRET reply"}],
           "usage": {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": cread,
                     "cache_creation_input_tokens": cwrite, "service_tier": "standard"}}
    msg.update(extra)
    return {"type": "assistant", "requestId": "req_" + mid, "version": "2.1.308", "message": msg}


class Transcript(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, *rows, raw=None):
        p = os.path.join(self.dir, "agent-a1.jsonl")
        with open(p, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
            if raw:
                f.write(raw)
        return p

    def test_one_request_split_over_lines_counts_once(self):
        p = self.write({"type": "user", "message": {"content": "SECRET prompt"}},
                       line("m1"), line("m1"), line("m2", inp=5, out=10, cread=0, cwrite=0))
        models, reason = ct.usage(p)
        self.assertIsNone(reason)
        self.assertEqual(models, {"claude-sonnet-5-5": {
            "input_tokens": 8, "output_tokens": 110, "cache_read_tokens": 1000, "cache_write_tokens": 50,
            "requests": 2}})

    def test_models_are_kept_apart_and_synthetic_messages_skipped(self):
        p = self.write(line("m1"), line("m2", model="claude-haiku-5-5", inp=1, out=1, cread=0, cwrite=0),
                       line("m3", model="<synthetic>", inp=0, out=0, cread=0, cwrite=0))
        models, _ = ct.usage(p)
        self.assertEqual(sorted(models), ["claude-haiku-5-5", "claude-sonnet-5-5"])

    def test_returns_numbers_and_model_names_only(self):
        models, _ = ct.usage(self.write(line("m1")))
        self.assertNotIn("SECRET", json.dumps(models))

    def test_unreadable_shapes_are_unavailable(self):
        cases = {
            "missing file": os.path.join(self.dir, "nope.jsonl"),
            "no requests": self.write({"type": "user", "message": {"content": "x"}}),
            "usage shape changed": self.write(line("m1"), {"type": "assistant", "message": {
                "id": "m2", "model": "claude-sonnet-5-5", "usage": {"tokens_in": 3}}}),
            "broken line": self.write(line("m1"), raw="{not json\n"),
        }
        for name, path in cases.items():
            with self.subTest(name):
                models, reason = ct.usage(path)
                self.assertIsNone(models)
                self.assertTrue(reason)


def payload(event, **kw):
    p = {"session_id": "s1", "transcript_path": "/x/s1.jsonl", "cwd": "/ws", "hook_event_name": event}
    p.update(kw)
    return p


class Adapter(unittest.TestCase):
    def setUp(self):
        self.env = {"TEMPLATE_VERSION": "0.8.0"}

    def events(self, p, **env):
        return t.claude_events(p, dict(self.env, **env), "ws")

    def test_session_start_and_end(self):
        [start] = self.events(payload("SessionStart", source="resume", model="claude-opus-5-5"))
        self.assertEqual((start["event_type"], start["run_id"]), ("run.started", "claude:s1"))
        self.assertEqual(start["payload"], {"runtime": "claude-code", "project_id": "ws", "source": "resume",
                                            "orchestrator_version": "0.8.0"})
        [end] = self.events(payload("SessionEnd", reason="other"))
        self.assertEqual((end["event_type"], end["payload"]["status"]), ("run.completed", "completed"))

    def test_subagent_start(self):
        [e] = self.events(payload("SubagentStart", agent_id="agent-a1", agent_type="api-dev"))
        self.assertEqual((e["event_type"], e["invocation_id"]), ("agent.started", "claude:a1"))
        self.assertEqual(e["payload"], {"agent_id": "a1", "agent_type": "api-dev", "runtime": "claude-code"})

    def test_background_launch_links_the_task_without_storing_the_prompt(self):
        p = payload("PostToolUse", tool_name="Agent", tool_use_id="toolu_1",
                    tool_input={"subagent_type": "api-dev", "model": "sonnet", "description": "login form",
                                "prompt": "Task: odd/tasks/login.md › T2 · Tier: normal\nSECRET brief"},
                    tool_response={"status": "async_launched", "agentId": "a1", "resolvedModel": "claude-sonnet-5-5",
                                   "prompt": "SECRET brief", "isAsync": True})
        [e] = self.events(p)
        self.assertEqual((e["event_type"], e["invocation_id"], e["task_id"]), ("agent.started", "claude:a1", "login#T2"))
        self.assertEqual(e["payload"]["model"], "claude-sonnet-5-5")
        self.assertNotIn("SECRET", json.dumps(e))

    def test_small_task_header(self):
        p = payload("PostToolUse", tool_name="Agent", tool_input={"prompt": "Task: fix-typo-1 · Tier: trivial\n..."},
                    tool_response={"status": "async_launched", "agentId": "a2"})
        self.assertEqual(self.events(p)[0]["task_id"], "fix-typo-1")

    def test_no_header_no_task(self):
        p = payload("PostToolUse", tool_name="Agent", tool_input={"prompt": "look around"},
                    tool_response={"status": "async_launched", "agentId": "a3"})
        self.assertIsNone(self.events(p)[0]["task_id"])

    def test_foreground_result_gives_duration_but_not_its_last_request_tokens(self):
        p = payload("PostToolUse", tool_name="Agent", tool_input={"subagent_type": "explorer"},
                    tool_response={"status": "completed", "agentId": "a1", "resolvedModel": "claude-haiku-5-5",
                                   "totalTokens": 12450, "totalDurationMs": 48211, "usage": {"input_tokens": 8320}})
        [e] = self.events(p)
        self.assertEqual(e["event_type"], "agent.completed")
        self.assertEqual((e["payload"]["duration_ms"], e["payload"]["duration_source"]), (48211, "runtime_reported"))
        self.assertFalse(any(k in e["payload"] for k in t.TOKENS))

    def test_subagent_stop_reads_its_transcript(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        tp = os.path.join(d, "agent-a1.jsonl")
        with open(tp, "w") as f:
            f.write(json.dumps(line("m1")) + "\n")
        stop = payload("SubagentStop", agent_id="a1", agent_type="api-dev", agent_transcript_path=tp,
                       last_assistant_message="SECRET")
        done, use = self.events(stop)
        self.assertEqual(done["event_type"], "agent.completed")
        self.assertEqual((use["event_type"], use["payload"]["source"], use["payload"]["input_tokens"],
                          use["payload"]["parser_version"]), ("usage.reported", "runtime_reported", 3, ct.PARSER_VERSION))
        self.assertNotIn("SECRET", json.dumps([done, use]))
        _, off = self.events(stop, TELEMETRY_TRANSCRIPTS="off")
        self.assertEqual((off["payload"]["source"], off["payload"]["input_tokens"]), ("unavailable", None))

    def test_failed_launch(self):
        [e] = self.events(payload("PostToolUseFailure", tool_name="Agent", tool_use_id="toolu_9", error="boom"))
        self.assertEqual((e["event_type"], e["invocation_id"]), ("agent.failed", "claude:toolu_9"))

    def test_other_hooks_and_tools_record_nothing(self):
        self.assertEqual(self.events(payload("PostToolUse", tool_name="Write")), [])
        self.assertEqual(self.events(payload("Stop")), [])

    def test_every_event_meets_the_contract(self):
        for e in self.events(payload("SessionStart", source="startup")) + self.events(payload("SessionEnd")):
            t.validate(e)


class Projection(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.s = t.Store(os.path.join(self.dir, "t.db"))

    def tearDown(self):
        self.s.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def rec(self, kind, inv, ts, task=None, key=None, **p):
        self.s.record(t.make_event(kind, "claude:s1", task_id=task, invocation_id=inv, payload=p, timestamp=ts, key=key))

    def test_a_late_launch_event_does_not_reopen_a_finished_agent(self):
        self.rec("agent.started", "claude:a1", "2026-11-03T10:00:00Z", agent_type="api-dev")
        self.rec("agent.completed", "claude:a1", "2026-11-03T10:01:00Z")
        self.rec("agent.started", "claude:a1", "2026-11-03T10:01:01Z", task="login#T2", key="launch")
        row = self.s.db.execute("SELECT status, started_at, task_id, duration_ms FROM agent_invocations").fetchone()
        self.assertEqual(row, ("completed", "2026-11-03T10:00:00.000Z", "login#T2", 60000))

    def test_a_later_attempt_at_the_same_task_is_a_retry(self):
        self.rec("agent.started", "claude:a1", "2026-11-03T10:00:00Z", task="login#T2", agent_type="api-dev")
        self.rec("agent.started", "claude:a2", "2026-11-03T11:00:00Z", task="login#T2", agent_type="api-dev")
        self.rec("agent.started", "claude:a3", "2026-11-03T11:30:00Z", task="login#T2", agent_type="explorer")
        rows = self.s.db.execute("SELECT invocation_id, retry_number, parent_invocation_id FROM agent_invocations "
                                 "ORDER BY invocation_id").fetchall()
        self.assertEqual(rows, [("claude:a1", 0, None), ("claude:a2", 1, "claude:a1"), ("claude:a3", 0, None)])

    def test_a_continued_agent_replaces_its_usage(self):
        for n, inp in ((1, 10), (2, 25)):
            self.rec("usage.reported", "claude:a1", "2026-11-03T10:0%d:00Z" % n, key="claude-sonnet-5-5@%d" % n,
                     source="runtime_reported", model="claude-sonnet-5-5", input_tokens=inp, requests=n)
        self.assertEqual(self.s.db.execute("SELECT count(*), sum(input_tokens) FROM usage_records").fetchone(), (1, 25))


class Hook(unittest.TestCase):
    def test_end_to_end(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        o = os.path.join(root, ".orchestrator")
        os.makedirs(os.path.join(o, "hooks"))
        shutil.copytree(os.path.join(TPL, "scripts"), os.path.join(o, "scripts"))
        shutil.copy(os.path.join(TPL, "hooks", "telemetry.sh"), os.path.join(o, "hooks"))
        with open(os.path.join(o, "orchestrator.conf"), "w") as f:
            f.write('TEMPLATE_VERSION="0.8.0"\n')
        script = os.path.join(o, "hooks", "telemetry.sh").replace("\\", "/")
        for p in (payload("SessionStart", source="startup"), payload("SubagentStart", agent_id="a1", agent_type="x")):
            r = subprocess.run([BASH, script, "hook", "claude"], input=json.dumps(p).encode(), capture_output=True,
                               timeout=60)
            self.assertEqual((r.returncode, r.stdout), (0, b""))
        with sqlite3.connect(os.path.join(o, "telemetry", "telemetry.db")) as db:
            self.assertEqual(db.execute("SELECT orchestrator_version, project_id FROM runs").fetchone(),
                             ("0.8.0", os.path.basename(root)))
            self.assertEqual(db.execute("SELECT count(*) FROM agent_invocations").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
