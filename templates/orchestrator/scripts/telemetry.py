#!/usr/bin/env python3
"""Local operational telemetry: the event contract and the SQLite store it projects into.
  python3 .orchestrator/scripts/telemetry.py ingest < events.json   (a JSON event, a list, or one per line)
Hooks call it through .orchestrator/hooks/telemetry.sh, which never fails the session and prints nothing.
The store is .orchestrator/telemetry/telemetry.db (ORCH_TELEMETRY_DB overrides it), errors go to errors.log next
to it, and each call logs its own duration in ingest_log, so the instrumentation's overhead is measured too.
Standard library only, no network and no model calls. Records metadata, never prompts, responses or file
content: each payload key must be in the contract, and its strings are short.
"""
import time

_T0 = time.perf_counter()

import datetime  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import sqlite3  # noqa: E402
import sys  # noqa: E402

SCHEMA_VERSION = 1
SOURCES = ("runtime_reported", "calculated", "estimated", "unavailable")
TOKENS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
MAX_STR = 200

# Event type -> (whether it needs an invocation_id, the payload keys it may carry).
_RUN = ("runtime", "runtime_version", "project_id", "orchestrator_version", "source", "status", "reason")
_TASK = ("title", "task_type", "status", "reason")
_AGENT = ("agent_id", "agent_type", "runtime", "model", "status", "duration_ms", "duration_source", "retry_number",
          "parent_invocation_id", "error")
EVENTS = {
    "run.started": (False, _RUN), "run.completed": (False, _RUN), "run.failed": (False, _RUN),
    "task.started": (False, _TASK), "task.completed": (False, _TASK), "task.failed": (False, _TASK),
    "agent.started": (True, _AGENT), "agent.completed": (True, _AGENT), "agent.failed": (True, _AGENT),
    "agent.retry": (True, _AGENT),
    "usage.reported": (True, ("model",) + TOKENS + ("source", "parser_version", "requests", "reason")),
    "criterion.verified": (False, ("criterion_code", "status", "verification_method")),
    "execution.blocked": (False, ("reason",)),
}
STATUSES = {
    "run": ("running", "completed", "failed"),
    "task": ("pending", "in_progress", "blocked", "done", "failed"),
    "agent": ("running", "success", "failed"),
    "criterion": ("passed", "failed", "blocked", "pending"),
}


def utc(ts=None):
    """An ISO 8601 timestamp with an offset or Z, as UTC with milliseconds; now when ts is None."""
    if ts is None:
        d = datetime.datetime.now(datetime.timezone.utc)
    else:
        try:
            d = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("timestamp is not ISO 8601")
        if d.tzinfo is None:
            raise ValueError("timestamp has no UTC offset")
    return d.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (d.microsecond // 1000)


def make_event(event_type, run_id, task_id=None, invocation_id=None, payload=None, timestamp=None, key=None):
    """A contract event. Its id hashes what identifies it (key, or else the timestamp), so a replay is a no-op."""
    ts = utc(timestamp)
    ident = json.dumps([run_id, event_type, task_id, invocation_id, ts if key is None else key])
    return {"event_id": "evt_" + hashlib.sha256(ident.encode()).hexdigest()[:24], "schema_version": SCHEMA_VERSION,
            "event_type": event_type, "timestamp": ts, "run_id": run_id, "task_id": task_id,
            "invocation_id": invocation_id, "payload": dict(payload or {})}


def validate(e):
    """The event, normalized, or ValueError naming the first rule it breaks (never quoting a value)."""
    if not isinstance(e, dict):
        raise ValueError("event is not an object")
    if e.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported schema_version")
    kind = e.get("event_type")
    if kind not in EVENTS:
        raise ValueError("unknown event_type")
    for k in ("event_id", "run_id"):
        if not isinstance(e.get(k), str) or not e[k]:
            raise ValueError("missing " + k)
    needs_inv, allowed = EVENTS[kind]
    if needs_inv and not e.get("invocation_id"):
        raise ValueError(kind + " needs invocation_id")
    p = e.get("payload") or {}
    if not isinstance(p, dict):
        raise ValueError("payload is not an object")
    for k, v in p.items():
        if k not in allowed:
            raise ValueError("payload key %r is not in the contract for %s" % (k, kind))
        if isinstance(v, str) and len(v) > MAX_STR:
            raise ValueError("payload key %r is longer than %d characters" % (k, MAX_STR))
        if v is not None and not isinstance(v, (str, int, float, bool)):
            raise ValueError("payload key %r is not a scalar" % k)
    for k in TOKENS + ("duration_ms", "requests", "retry_number"):
        if p.get(k) is not None and (not isinstance(p[k], int) or isinstance(p[k], bool) or p[k] < 0):
            raise ValueError(k + " is not a non-negative integer")
    if kind == "usage.reported":
        if p.get("source") not in SOURCES:
            raise ValueError("usage source is not one of " + ", ".join(SOURCES))
        if p["source"] == "unavailable" and any(p.get(k) is not None for k in TOKENS):
            raise ValueError("usage marked unavailable carries tokens")
    if p.get("duration_source") is not None and p["duration_source"] not in SOURCES:
        raise ValueError("duration_source is not one of " + ", ".join(SOURCES))
    group = {"run": "run", "tas": "task", "age": "agent", "cri": "criterion"}.get(kind[:3])
    if group and p.get("status") is not None and p["status"] not in STATUSES[group]:
        raise ValueError("status is not one of " + ", ".join(STATUSES[group]))
    if kind == "criterion.verified" and (not e.get("task_id") or not p.get("criterion_code") or not p.get("status")):
        raise ValueError("criterion.verified needs task_id, criterion_code and status")
    return dict(e, timestamp=utc(e.get("timestamp")), payload=p)


MIGRATIONS = [(1, """
CREATE TABLE runs (run_id TEXT PRIMARY KEY, project_id TEXT, runtime TEXT, runtime_version TEXT,
  orchestrator_version TEXT, started_at TEXT, finished_at TEXT, status TEXT, total_duration_ms INTEGER,
  starts INTEGER NOT NULL DEFAULT 0);
CREATE TABLE tasks (task_id TEXT PRIMARY KEY, run_id TEXT, title TEXT, task_type TEXT, status TEXT,
  started_at TEXT, finished_at TEXT);
CREATE TABLE agent_invocations (invocation_id TEXT PRIMARY KEY, run_id TEXT, task_id TEXT, agent_id TEXT,
  agent_type TEXT, runtime TEXT, model TEXT, started_at TEXT, finished_at TEXT, status TEXT, duration_ms INTEGER,
  duration_source TEXT, retry_number INTEGER NOT NULL DEFAULT 0, parent_invocation_id TEXT, error TEXT);
CREATE TABLE usage_records (usage_id TEXT PRIMARY KEY, invocation_id TEXT, run_id TEXT, model TEXT,
  input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER, cache_write_tokens INTEGER,
  requests INTEGER, source TEXT NOT NULL, parser_version TEXT, reason TEXT, captured_at TEXT);
CREATE TABLE criteria (criterion_id TEXT PRIMARY KEY, task_id TEXT, run_id TEXT, criterion_code TEXT, status TEXT,
  verification_method TEXT, verified_at TEXT);
CREATE TABLE events (event_id TEXT PRIMARY KEY, schema_version INTEGER, event_type TEXT, timestamp TEXT,
  run_id TEXT, task_id TEXT, invocation_id TEXT, payload_json TEXT, received_at TEXT);
CREATE TABLE ingest_log (id INTEGER PRIMARY KEY, at TEXT, command TEXT, events INTEGER, recorded INTEGER,
  elapsed_ms REAL, ok INTEGER, error TEXT);
CREATE INDEX invocations_by_run ON agent_invocations (run_id);
CREATE INDEX invocations_by_task ON agent_invocations (task_id);
CREATE INDEX usage_by_invocation ON usage_records (invocation_id);
CREATE INDEX events_by_run ON events (run_id);
""")]


def _ms_between(a, b):
    if not a or not b:
        return None
    f = "%Y-%m-%dT%H:%M:%S.%fZ"
    return int((datetime.datetime.strptime(b, f) - datetime.datetime.strptime(a, f)).total_seconds() * 1000)


class Store:
    def __init__(self, path):
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=2, isolation_level=None)
        self.db.execute("PRAGMA busy_timeout = 2000")
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.execute("PRAGMA synchronous = NORMAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT)")
        done = {r[0] for r in self.db.execute("SELECT version FROM schema_migrations")}
        for version, sql in MIGRATIONS:
            if version in done:
                continue
            self.db.execute("BEGIN IMMEDIATE")
            try:
                for stmt in sql.split(";"):
                    if stmt.strip():
                        self.db.execute(stmt)
                self.db.execute("INSERT INTO schema_migrations VALUES (?, ?)", (version, utc()))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    def close(self):
        self.db.close()

    def record(self, event):
        """Store and project one event. False when it was already recorded (same event_id)."""
        e = validate(event)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (e["event_id"], e["schema_version"], e["event_type"], e["timestamp"], e["run_id"], e.get("task_id"),
                 e.get("invocation_id"), json.dumps(e["payload"], sort_keys=True), utc()))
            if cur.rowcount:
                self._project(e)
            self.db.execute("COMMIT")
            return bool(cur.rowcount)
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def log_ingest(self, command, events, recorded, ok, error=None):
        self.db.execute("INSERT INTO ingest_log (at, command, events, recorded, elapsed_ms, ok, error) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (utc(), command, events, recorded, round((time.perf_counter() - _T0) * 1000, 2), int(ok), error))

    def _project(self, e):
        x, kind, p, ts, run = self.db.execute, e["event_type"], e["payload"], e["timestamp"], e["run_id"]
        task, inv = e.get("task_id"), e.get("invocation_id")
        if task:
            x("INSERT OR IGNORE INTO tasks (task_id, run_id, started_at, status) VALUES (?, ?, ?, 'in_progress')",
              (task, run, ts))
        if kind == "run.started":
            # A resumed or compacted session is the same run: it reopens, keeping its first start.
            x("INSERT OR IGNORE INTO runs (run_id, started_at) VALUES (?, ?)", (run, ts))
            x("UPDATE runs SET status = 'running', finished_at = NULL, total_duration_ms = NULL, starts = starts + 1, "
              "runtime = coalesce(?, runtime), runtime_version = coalesce(?, runtime_version), "
              "project_id = coalesce(?, project_id), orchestrator_version = coalesce(?, orchestrator_version) "
              "WHERE run_id = ?",
              (p.get("runtime"), p.get("runtime_version"), p.get("project_id"), p.get("orchestrator_version"), run))
        elif kind in ("run.completed", "run.failed"):
            x("INSERT OR IGNORE INTO runs (run_id) VALUES (?)", (run,))
            started = x("SELECT started_at FROM runs WHERE run_id = ?", (run,)).fetchone()[0]
            x("UPDATE runs SET finished_at = ?, status = ?, total_duration_ms = ? WHERE run_id = ?",
              (ts, p.get("status") or kind.split(".")[1], _ms_between(started, ts), run))
        elif kind.startswith("task.") and task:
            status = p.get("status") or {"task.started": "in_progress", "task.completed": "done"}.get(kind, "failed")
            x("UPDATE tasks SET status = ?, title = coalesce(?, title), task_type = coalesce(?, task_type), "
              "finished_at = ? WHERE task_id = ?",
              (status, p.get("title"), p.get("task_type"), None if kind == "task.started" else ts, task))
        elif kind == "execution.blocked" and task:
            x("UPDATE tasks SET status = 'blocked' WHERE task_id = ?", (task,))
        elif kind.startswith("agent."):
            x("INSERT OR IGNORE INTO agent_invocations (invocation_id, run_id) VALUES (?, ?)", (inv, run))
            x("UPDATE agent_invocations SET task_id = coalesce(?, task_id), agent_id = coalesce(?, agent_id), "
              "agent_type = coalesce(?, agent_type), runtime = coalesce(?, runtime), model = coalesce(?, model), "
              "retry_number = coalesce(?, retry_number), parent_invocation_id = coalesce(?, parent_invocation_id) "
              "WHERE invocation_id = ?",
              (task, p.get("agent_id"), p.get("agent_type"), p.get("runtime"), p.get("model"), p.get("retry_number"),
               p.get("parent_invocation_id"), inv))
            if kind == "agent.started":
                x("UPDATE agent_invocations SET started_at = ?, status = 'running' WHERE invocation_id = ?", (ts, inv))
            elif kind in ("agent.completed", "agent.failed"):
                started = x("SELECT started_at FROM agent_invocations WHERE invocation_id = ?", (inv,)).fetchone()[0]
                dur, src = p.get("duration_ms"), p.get("duration_source") or "runtime_reported"
                if dur is None:
                    dur, src = _ms_between(started, ts), "calculated"
                x("UPDATE agent_invocations SET finished_at = ?, status = ?, duration_ms = ?, duration_source = ?, "
                  "error = coalesce(?, error) WHERE invocation_id = ?",
                  (ts, p.get("status") or ("success" if kind == "agent.completed" else "failed"), dur,
                   src if dur is not None else None, p.get("error"), inv))
        elif kind == "usage.reported":
            x("INSERT OR REPLACE INTO usage_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
              ("use_" + e["event_id"][4:], inv, run, p.get("model")) + tuple(p.get(k) for k in TOKENS)
              + (p.get("requests"), p["source"], p.get("parser_version"), p.get("reason"), ts))
        elif kind == "criterion.verified":
            cid = "%s#%s" % (task, p["criterion_code"])
            last = x("SELECT verified_at FROM criteria WHERE criterion_id = ?", (cid,)).fetchone()
            if last is None or last[0] <= ts:
                x("INSERT OR REPLACE INTO criteria VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (cid, task, run, p["criterion_code"], p["status"], p.get("verification_method"), ts))


def db_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.environ.get("ORCH_TELEMETRY_DB") or os.path.join(os.path.dirname(here), "telemetry", "telemetry.db")


def _note_error(path, command, err):
    """One line in errors.log: when, which command, the error's class and message (never the input)."""
    try:
        with open(os.path.join(os.path.dirname(path), "errors.log"), "a") as f:
            f.write("%s %s %s: %s\n" % (utc(), command, type(err).__name__, str(err)[:MAX_STR].replace("\n", " ")))
    except Exception:
        pass


def _read_events(text):
    text = text.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except ValueError:
        data = [json.loads(line) for line in text.splitlines() if line.strip()]
    return data if isinstance(data, list) else [data]


def ingest(stdin_text, path):
    store, events, recorded = None, [], 0
    try:
        events = _read_events(stdin_text)
        store = Store(path)
        for e in events:
            recorded += store.record(e)
        store.log_ingest("ingest", len(events), recorded, True)
    except Exception as err:
        _note_error(path, "ingest", err)
        if store is not None:
            try:
                store.log_ingest("ingest", len(events), recorded, False, type(err).__name__)
            except Exception:
                pass
    finally:
        if store is not None:
            store.close()


def main(argv):
    if len(argv) < 2 or argv[1] not in ("ingest",):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    path = db_path()
    if not os.path.isdir(os.path.dirname(path)):
        try:
            os.makedirs(os.path.dirname(path))
        except OSError:
            return 0
    ingest(sys.stdin.read(), path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
