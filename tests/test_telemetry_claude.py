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

    def test_a_streamed_request_keeps_its_final_output(self):
        # Observed in real transcripts: a request's lines repeat its usage, output_tokens growing while it streams.
        models, reason = ct.usage(self.write(line("m1", out=21), line("m1", out=396), line("m1", out=396)))
        self.assertIsNone(reason)
        self.assertEqual((models["claude-sonnet-5-5"]["output_tokens"], models["claude-sonnet-5-5"]["requests"]),
                         (396, 1))

    def test_inconsistent_repeats_are_unavailable(self):
        cases = {
            "model changes": (line("m1"), line("m1", model="claude-opus-5-5")),
            "input changes": (line("m1"), line("m1", inp=4)),
            "cache changes": (line("m1"), line("m1", cread=999)),
            "output shrinks": (line("m1", out=100), line("m1", out=99)),
        }
        for name, rows in cases.items():
            with self.subTest(name):
                models, reason = ct.usage(self.write(*rows))
                self.assertIsNone(models)
                self.assertIn("inconsistent", reason)

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

    def test_real_header_variants(self):
        # Shapes taken from real orchestrator briefs (feature names changed).
        cases = {
            "Task: odd/tasks/login.md › T2 review · Tier: normal": "login#T2",
            "Task: odd/tasks/login.md › T1 (TL review round 1) · Tier: normal": "login#T1",
            "Task: odd/tasks/login.md · Tier: normal": "login",
            "Task: fix-typo-1 · Tier: trivial": "fix-typo-1",
            "\n  Task: odd/tasks/login.md › T3 · Tier: hard\nbody": "login#T3",
            "Context first\nTask: odd/tasks/login.md › T2 · Tier: normal": None,
            "Task: odd/tasks/login.md › T2\n· Tier: normal": None,
        }
        for prompt, want in cases.items():
            with self.subTest(prompt):
                p = payload("PostToolUse", tool_name="Agent", tool_input={"prompt": prompt},
                            tool_response={"status": "async_launched", "agentId": "a9"})
                self.assertEqual(self.events(p)[0]["task_id"], want)

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

    def test_subagent_stop_defers_its_transcript(self):
        # Live check on Claude Code 2.1.308: at SubagentStop the transcript may still lack the final request, so the
        # stop records the agent's end only; the usage is read later (Deferred below).
        stop = payload("SubagentStop", agent_id="a1", agent_type="api-dev", agent_transcript_path="/x/agent-a1.jsonl",
                       last_assistant_message="SECRET")
        [done] = self.events(stop)
        self.assertEqual(done["event_type"], "agent.completed")
        self.assertNotIn("SECRET", json.dumps(done))
        _, off = self.events(stop, TELEMETRY_TRANSCRIPTS="off")
        self.assertEqual((off["payload"]["source"], off["payload"].get("input_tokens")), ("unavailable", None))
        _, nopath = self.events(payload("SubagentStop", agent_id="a1", agent_type="api-dev"))
        self.assertEqual(nopath["payload"]["source"], "unavailable")

    def test_failed_launch_keeps_category_and_duration_only(self):
        for interrupt, category in ((False, "error"), (True, "interrupt")):
            with self.subTest(category):
                [e] = self.events(payload("PostToolUseFailure", tool_name="Agent", tool_use_id="toolu_9",
                                          tool_input={"subagent_type": "api-dev", "prompt": "Task: login-1 · Tier: x"},
                                          error="Permission denied: SECRET path", is_interrupt=interrupt,
                                          duration_ms=4187))
                self.assertEqual((e["event_type"], e["invocation_id"]), ("agent.failed", "claude:tool:toolu_9"))
                self.assertEqual(e["payload"]["error"], category)
                self.assertEqual((e["payload"]["duration_ms"], e["payload"]["duration_source"]),
                                 (4187, "runtime_reported"))
                self.assertNotIn("agent_id", e["payload"])
                self.assertNotIn("SECRET", json.dumps(e))

    def test_claude_code_internal_agents_are_not_recorded(self):
        # SubagentStop also fires for Claude Code's own agents (prompt suggestions, /btw), with agent_type "" when
        # the session runs without --agent (hooks reference). Agent-tool subagents always carry their name.
        for kind in ("SubagentStart", "SubagentStop"):
            with self.subTest(kind):
                self.assertEqual(self.events(payload(kind, agent_id="a1", agent_type="")), [])
        self.assertEqual(len(self.events(payload("SubagentStart", agent_id="a1"))), 1)  # absent is not empty

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
        self.rec("agent.started", "claude:a1", "2026-11-03T10:00:00Z", task="login#T2", agent_type="api-dev", agent_id="a1")
        self.rec("agent.started", "claude:a2", "2026-11-03T11:00:00Z", task="login#T2", agent_type="api-dev", agent_id="a2")
        self.rec("agent.started", "claude:a3", "2026-11-03T11:30:00Z", task="login#T2", agent_type="explorer", agent_id="a3")
        rows = self.s.db.execute("SELECT invocation_id, retry_number, parent_invocation_id FROM agent_invocations "
                                 "ORDER BY invocation_id").fetchall()
        self.assertEqual(rows, [("claude:a1", 0, None), ("claude:a2", 1, "claude:a1"), ("claude:a3", 0, None)])

    def test_a_launch_that_never_started_is_not_an_attempt(self):
        self.rec("agent.failed", "claude:tool:toolu_9", "2026-11-03T10:00:00Z", task="login#T2", agent_type="api-dev",
                 error="error")
        self.rec("agent.started", "claude:a2", "2026-11-03T10:05:00Z", task="login#T2", agent_type="api-dev",
                 agent_id="a2")
        self.rec("agent.started", "claude:a3", "2026-11-03T10:30:00Z", task="login#T2", agent_type="api-dev",
                 agent_id="a3")
        rows = self.s.db.execute("SELECT invocation_id, retry_number, parent_invocation_id FROM agent_invocations "
                                 "ORDER BY invocation_id").fetchall()
        self.assertEqual(rows, [("claude:a2", 0, None), ("claude:a3", 1, "claude:a2"),
                                ("claude:tool:toolu_9", 0, None)])

    def test_a_continued_agent_replaces_its_usage(self):
        for n, inp in ((1, 10), (2, 25)):
            self.rec("usage.reported", "claude:a1", "2026-11-03T10:0%d:00Z" % n, key="claude-sonnet-5-5@%d" % n,
                     source="runtime_reported", model="claude-sonnet-5-5", input_tokens=inp, requests=n)
        self.assertEqual(self.s.db.execute("SELECT count(*), sum(input_tokens) FROM usage_records").fetchone(), (1, 25))


class Lifecycle(unittest.TestCase):
    """Whole hook sequences through the adapter into the store: one invocation per agent, no false retries."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.s = t.Store(os.path.join(self.dir, "t.db"))
        self.tp = os.path.join(self.dir, "agent-a1.jsonl")
        with open(self.tp, "w") as f:
            f.write(json.dumps(line("m1")) + "\n")

    def tearDown(self):
        self.s.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def feed(self, *payloads):
        for p in payloads:
            t.claude_hook(self.s, p, {}, "ws")
        return self.s.db.execute("SELECT invocation_id, task_id, status, retry_number FROM agent_invocations "
                                 "ORDER BY invocation_id").fetchall()

    def agent(self, status, aid="a1"):
        start = payload("SubagentStart", agent_id=aid, agent_type="api-dev")
        stop = payload("SubagentStop", agent_id=aid, agent_type="api-dev", agent_transcript_path=self.tp)
        result = payload("PostToolUse", tool_name="Agent", tool_use_id="toolu_" + aid,
                         tool_input={"subagent_type": "api-dev", "prompt": "Task: odd/tasks/login.md › T2 · Tier: n"},
                         tool_response={"status": status, "agentId": aid, "totalDurationMs": 5})
        return start, stop, result

    def test_background_and_foreground_in_any_order(self):
        for status, order in (("async_launched", (0, 2, 1)), ("async_launched", (2, 0, 1)), ("completed", (0, 1, 2)),
                              ("completed", (2, 1, 0))):
            with self.subTest(status=status, order=order):
                for table in ("agent_invocations", "events", "usage_records", "claude_pending"):
                    self.s.db.execute("DELETE FROM " + table)
                ev = self.agent(status)
                rows = self.feed(*(ev[i] for i in order), payload("SessionEnd"))
                self.assertEqual(rows, [("claude:a1", "login#T2", "completed", 0)])
                self.assertEqual(self.s.db.execute("SELECT count(*) FROM usage_records WHERE source = "
                                                   "'runtime_reported'").fetchone()[0], 1)

    def test_a_failed_launch_then_the_real_one_and_an_internal_agent(self):
        failed = payload("PostToolUseFailure", tool_name="Agent", tool_use_id="toolu_0",
                         tool_input={"subagent_type": "api-dev", "prompt": "Task: odd/tasks/login.md › T2 · Tier: n"},
                         error="denied", is_interrupt=False)
        internal = payload("SubagentStop", agent_id="int1", agent_type="", agent_transcript_path=self.tp)
        rows = self.feed(failed, internal, *self.agent("async_launched"))
        self.assertEqual(rows, [("claude:a1", "login#T2", "completed", 0),
                                ("claude:tool:toolu_0", "login#T2", "failed", 0)])


class Deferred(unittest.TestCase):
    """A subagent's usage is read once its transcript has caught up: by a later hook of the session (2 s after the
    stop at least), at SessionEnd, or at the next SessionStart for a session that ended without one."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.s = t.Store(os.path.join(self.dir, "t.db"))
        self.tp = os.path.join(self.dir, "agent-a1.jsonl")
        with open(self.tp, "w") as f:
            f.write(json.dumps(line("m1", out=82)) + "\n")  # the final request isn't written yet

    def tearDown(self):
        self.s.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def hook(self, p, at):
        t.claude_hook(self.s, p, {}, "ws", now="2026-11-03T10:00:%02dZ" % at)

    def stop(self, at, aid="a1", session="s1"):
        self.hook(payload("SubagentStop", session_id=session, agent_id=aid, agent_type="api-dev",
                          agent_transcript_path=self.tp), at)

    def finish_transcript(self):
        with open(self.tp, "a") as f:
            f.write(json.dumps(line("m2", out=4)) + "\n")

    def usage(self):
        return self.s.db.execute("SELECT source, output_tokens, requests, reason FROM usage_records").fetchall()

    def pending(self):
        return self.s.db.execute("SELECT count(*) FROM claude_pending").fetchone()[0]

    def test_session_end_reads_the_caught_up_transcript(self):
        self.stop(0)
        self.assertEqual((self.usage(), self.pending()), ([], 1))
        self.finish_transcript()
        self.hook(payload("SessionEnd"), 1)
        self.assertEqual((self.usage(), self.pending()), ([("runtime_reported", 86, 2, None)], 0))

    def test_a_later_hook_reads_it_only_after_two_seconds(self):
        self.stop(0)
        self.finish_transcript()
        self.hook(payload("SubagentStart", agent_id="a2", agent_type="x"), 1)
        self.assertEqual(self.usage(), [])
        self.hook(payload("SubagentStart", agent_id="a3", agent_type="x"), 3)
        self.assertEqual(self.usage(), [("runtime_reported", 86, 2, None)])

    def test_session_end_records_unavailable_when_it_still_cannot_read(self):
        os.remove(self.tp)
        self.stop(0)
        self.hook(payload("SessionEnd"), 1)
        self.assertEqual(self.usage(), [("unavailable", None, None, "transcript not readable")])
        self.assertEqual(self.pending(), 0)

    def test_the_next_session_reads_what_a_killed_one_left(self):
        self.stop(0, session="dead")
        self.finish_transcript()
        self.hook(payload("SessionStart", session_id="next", source="startup"), 1)
        self.assertEqual(self.usage(), [("runtime_reported", 86, 2, None)])

    def test_real_usage_replaces_an_earlier_unavailable(self):
        self.s.record(t.make_event("usage.reported", "claude:s1", invocation_id="claude:a1", key="unavailable",
                                   payload={"source": "unavailable", "reason": "x"}))
        self.stop(0)
        self.finish_transcript()
        self.hook(payload("SessionEnd"), 1)
        self.assertEqual(self.usage(), [("runtime_reported", 86, 2, None)])

    def test_a_continued_agent_is_read_again(self):
        self.stop(0)
        self.hook(payload("SessionEnd"), 1)
        self.finish_transcript()
        self.stop(5)
        self.hook(payload("SessionEnd"), 6)
        self.assertEqual(self.usage(), [("runtime_reported", 86, 2, None)])


class HookConfig(unittest.TestCase):
    """claude -p kills async hooks still running at teardown (hooks reference, "async hooks"), so every telemetry hook
    whose event can come last is synchronous, with a timeout short enough not to hold the session's exit."""

    def test_events_that_can_end_a_session_are_synchronous_and_bounded(self):
        with open(os.path.join(os.path.dirname(HERE), "templates", "claude", "settings.json")) as f:
            hooks = json.load(f)["hooks"]
        seen = set()
        for event, groups in hooks.items():
            for g in groups:
                for h in g["hooks"]:
                    if "telemetry.sh" not in h["command"]:
                        continue
                    seen.add(event)
                    self.assertLessEqual(h.get("timeout", 600), 5, event)
                    if event != "SessionStart":
                        self.assertFalse(h.get("async"), event)
        self.assertEqual(seen, {"SessionStart", "SessionEnd", "SubagentStart", "SubagentStop", "PostToolUse",
                                "PostToolUseFailure"})


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
