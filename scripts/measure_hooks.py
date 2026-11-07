#!/usr/bin/env python3
"""Hook latency, concurrency and privacy of the telemetry hooks, measured end to end (phase 1 review, R3).
  python3 scripts/measure_hooks.py <scaffolded workspace> <main transcript> <subagent transcript>
Scaffold a throwaway workspace first (bash scripts/scaffold.sh --git <dir>). Transcripts are read for figures
only, as the hooks do; nothing of them is printed. No network, no model calls.
"""
import concurrent.futures as cf
import json
import os
import sqlite3
import statistics
import subprocess
import sys
import time

ws, main_tp, sub_tp = sys.argv[1], sys.argv[2], sys.argv[3]
hook = os.path.join(ws, ".orchestrator/hooks/telemetry.sh")
def run(p):
    t0 = time.perf_counter()
    r = subprocess.run(["bash", hook, "hook", "claude"], input=json.dumps(p).encode(), capture_output=True)
    return (time.perf_counter() - t0) * 1000, r.stdout
res = {}
def m(name, p):
    ms, out = run(p); res.setdefault(name, []).append(ms); assert out == b"", out
for i in range(20):
    sid = "bench-%d" % i
    m("SessionStart", {"hook_event_name": "SessionStart", "session_id": sid, "source": "startup", "transcript_path": "/nonexistent"})
    m("SubagentStart", {"hook_event_name": "SubagentStart", "session_id": sid, "agent_id": "a%d" % i, "agent_type": "api-dev"})
    m("PostToolUse", {"hook_event_name": "PostToolUse", "session_id": sid, "tool_name": "Agent", "tool_input": {"prompt": "Task: odd/tasks/x.md › T1 · Tier: normal\nsecret body", "subagent_type": "api-dev"}, "tool_response": {"agentId": "a%d" % i, "status": "completed", "totalDurationMs": 1000}})
    m("SubagentStop", {"hook_event_name": "SubagentStop", "session_id": sid, "agent_id": "a%d" % i, "agent_type": "api-dev", "agent_transcript_path": sub_tp})
    m("SessionEnd", {"hook_event_name": "SessionEnd", "session_id": sid, "reason": "exit"})
# worst case: SessionEnd reading the largest real main transcript
for i in range(5):
    sid = "big-%d" % i
    run({"hook_event_name": "SessionStart", "session_id": sid, "source": "startup", "transcript_path": main_tp})
    m("SessionEnd (41 MB main transcript)", {"hook_event_name": "SessionEnd", "session_id": sid, "reason": "exit"})
for k, v in res.items():
    v = sorted(v); print("%-38s n=%2d p50 %6.0f ms  p95 %6.0f ms  max %6.0f ms" % (k, len(v), statistics.median(v), v[int(len(v)*0.95)-1], v[-1]))
# concurrency: 8 subagents stop at once in one session
sid = "par"
run({"hook_event_name": "SessionStart", "session_id": sid, "source": "startup", "transcript_path": "/nonexistent"})
with cf.ThreadPoolExecutor(8) as ex:
    times = list(ex.map(lambda i: run({"hook_event_name": "SubagentStop", "session_id": sid, "agent_id": "p%d" % i, "agent_type": "api-dev", "agent_transcript_path": sub_tp})[0], range(8)))
run({"hook_event_name": "SessionEnd", "session_id": sid, "reason": "exit"})
db = sqlite3.connect(os.path.join(ws, ".orchestrator/telemetry/telemetry.db"))
print("parallel stops: max %.0f ms; invocations %d, with usage %d" % (max(times),
      db.execute("select count(*) from agent_invocations where run_id='claude:par' and agent_type<>'main'").fetchone()[0],
      db.execute("select count(distinct invocation_id) from usage_records where run_id='claude:par' and invocation_id not like '%:main'").fetchone()[0]))
print("ingest_log in-process ms: p50 %.1f p95 %.1f; failures %d" % tuple(
      [statistics.median([r[0] for r in db.execute("select elapsed_ms from ingest_log")]),
       sorted([r[0] for r in db.execute("select elapsed_ms from ingest_log")])[int(db.execute("select count(*) from ingest_log").fetchone()[0]*0.95)-1],
       db.execute("select count(*) from ingest_log where ok=0").fetchone()[0]]))
print("errors.log:", open(os.path.join(ws, ".orchestrator/telemetry/errors.log")).read() if os.path.exists(os.path.join(ws, ".orchestrator/telemetry/errors.log")) else "none")
blob = "\n".join(r[0] for r in db.execute("select payload_json from events"))
print("prompt body stored:", "secret body" in blob, "| transcript paths in events:", main_tp in blob or sub_tp in blob)
print("pending left:", db.execute("select count(*) from claude_pending").fetchone()[0])
