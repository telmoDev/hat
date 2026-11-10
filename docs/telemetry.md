# Telemetry contract

The local operational telemetry of a workspace (F1, *Operational Intelligence*): what it records, where, how,
and what it never records. The code is the reference (`templates/orchestrator/scripts/telemetry.py`);
`tests/test_telemetry_doc.py` fails when this document and the code disagree.

Event schema version: 1 · Store migrations: 2 · Claude transcript parser: `claude-transcript/2`

## Principles

- **Local and silent.** A SQLite file per workspace, standard library only, no network, no model calls. Hooks
  never fail or block a session and print nothing.
- **Metadata, never content.** No prompt, response, tool input, file content, diff or error text is stored. Each
  event type accepts only the payload keys listed below, as scalars, strings at most 200 characters.
- **A figure has a source.** Tokens and durations are recorded with where they came from; when they can't be
  read reliably they are `unavailable`, never estimated or zero.
- **Markdown stays the source of truth.** Task files and memory are projected into the store, never written by it.

## Identifiers

| Id | Shape | Example |
|---|---|---|
| `run_id` | one runtime session: `claude:<session id>` | `claude:5f1c…` |
| `invocation_id` | one agent run: `claude:<agent id>`; the session's own (main) run `claude:<session id>:main`; an Agent call that failed before a subagent existed `claude:tool:<tool use id>` | `claude:a1b2…` |
| `task_id` | an ODD task: `<feature>#T<n>` (task file), or `<feature>` / `<feature>-<n>` (small-task brief header) | `checkout#T2` |
| `criterion_id` | `<task_id>#O<n>` | `checkout#T2#O1` |
| `event_id` | `evt_` + 24 hex of a SHA-256 over what identifies the event (run, type, task, invocation, and a key or the timestamp) | replaying an event is a no-op |

## Events

Every event: `event_id`, `schema_version` (1), `event_type`, `timestamp` (ISO 8601 with an offset, stored as UTC
with milliseconds), `run_id`, optional `task_id` and `invocation_id`, and `payload`.

| Event type | Needs `invocation_id` | Payload keys |
|---|---|---|
| `run.started` | no | `runtime`, `runtime_version`, `project_id`, `orchestrator_version`, `source`, `status`, `reason` |
| `run.completed` | no | `runtime`, `runtime_version`, `project_id`, `orchestrator_version`, `source`, `status`, `reason` |
| `run.failed` | no | `runtime`, `runtime_version`, `project_id`, `orchestrator_version`, `source`, `status`, `reason` |
| `task.started` | no | `title`, `task_type`, `status`, `reason` |
| `task.completed` | no | `title`, `task_type`, `status`, `reason` |
| `task.failed` | no | `title`, `task_type`, `status`, `reason` |
| `agent.started` | yes | `agent_id`, `agent_type`, `runtime`, `model`, `status`, `duration_ms`, `duration_source`, `retry_number`, `parent_invocation_id`, `error` |
| `agent.completed` | yes | `agent_id`, `agent_type`, `runtime`, `model`, `status`, `duration_ms`, `duration_source`, `retry_number`, `parent_invocation_id`, `error` |
| `agent.failed` | yes | `agent_id`, `agent_type`, `runtime`, `model`, `status`, `duration_ms`, `duration_source`, `retry_number`, `parent_invocation_id`, `error` |
| `agent.retry` | yes | `agent_id`, `agent_type`, `runtime`, `model`, `status`, `duration_ms`, `duration_source`, `retry_number`, `parent_invocation_id`, `error` |
| `usage.reported` | yes | `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `source`, `parser_version`, `requests`, `reason` |
| `criterion.verified` | no | `criterion_code`, `status`, `verification_method` |
| `execution.blocked` | no | `reason` |

Validation rejects, naming the rule and never quoting a value: an unknown type or key, a non-scalar value, a
string over 200 characters, a negative or non-integer count (`*_tokens`, `duration_ms`, `requests`,
`retry_number`), a status outside its list, `usage.reported` without a valid `source` or marked `unavailable`
while carrying tokens, and `criterion.verified` without `task_id`, `criterion_code` and `status`.

## Statuses

| Group | Values |
|---|---|
| run | `running`, `completed`, `failed` |
| task | `pending`, `in_progress`, `blocked`, `done`, `failed` |
| agent | `running`, `completed`, `success`, `failed` |
| criterion | `passed`, `failed`, `blocked`, `pending` |

## Figures and their sources

Token kinds: `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, plus `requests`.

| Source | Meaning |
|---|---|
| `runtime_reported` | read from what the runtime itself wrote (the Claude transcript, a tool result's duration) |
| `calculated` | derived from recorded times (a duration from start and stop hooks) |
| `estimated` | reserved; nothing records it today |
| `unavailable` | couldn't be read reliably; tokens are NULL and `reason` says why |

- One usage row per invocation and model. A continued agent reports new totals, which replace the old ones. A
  later `unavailable` never hides figures already read; real figures replace an earlier `unavailable`.
- A reported duration beats one calculated from hook times.
- Cost: `telemetry.py cost` prices only `runtime_reported` usage at the rates in `.orchestrator/rates.json`
  (empty in the template), labelled an API-equivalent estimate, never subscription spend.

## Claude Code adapter

Hooks in `.claude/settings.json` call `.orchestrator/hooks/telemetry.sh hook claude`, which runs `telemetry.py`
with a 5 s timeout. SessionStart runs async so it doesn't delay the start; the others run synchronously
because `claude -p` kills async hooks before they finish.

| Hook | Events |
|---|---|
| `SessionStart` | `run.started` (a resumed or compacted session reopens the same run); `agent.started` for the main invocation; queues the main transcript; final read of anything still pending from earlier sessions; criteria sync |
| `SubagentStart` | `agent.started` (skipped for Claude Code's internal agents, whose `agent_type` is empty) |
| `PostToolUse` (Agent) | `agent.started` with the task from the brief's `Task: … · Tier: …` header (background launch) or `agent.completed` with the runtime-reported duration (foreground result; its token figures cover only the last request and are not recorded) |
| `PostToolUseFailure` (Agent) | `agent.failed` for `claude:tool:<id>`: category (`error` or `interrupt`) and duration only |
| `SubagentStop` | `agent.completed`; queues the transcript, read once 2 s old (the transcript lags the hook) |
| `SessionEnd` | `run.completed`, main `agent.completed`, reads the queued transcripts, criteria sync |

Transcripts (`claude_transcript.py`, `claude-transcript/2`) are a private format, so the parser is strict: any
line or usage shape it doesn't know makes the whole invocation `unavailable` instead of a partial sum; a request
repeated on several lines counts once with its largest output, and any other difference between them is
`unavailable`. When a Claude Code release changes the shape, the parser version is bumped with the fix.

**Codex**: not recorded. Its adapter waits for real, verified hook payloads (no invented fields, no assumed
equivalence with Claude Code).

## Recovery and idempotency

- Replaying any event is a no-op (deterministic `event_id`, `INSERT OR IGNORE`).
- A transcript unreadable at its first chance stays queued (`claude_pending`): a subagent's until its session
  ends, the main session's until the next session starts, which makes the last attempt and records
  `unavailable` if it still can't read it. A session killed without `SessionEnd` is recovered the same way.
- Start events arriving after a stop never reopen a finished invocation; a stop without a start still records it.
- Attempts: `retry_number` and `parent_invocation_id` count earlier invocations of the same agent type on the same
  task.

## Scope

Every metric belongs to one project: the store lives in that workspace, `project_id` names it, and nothing reads
or writes another workspace's store. There is no global store. A global view (meta-harness phase 2) may only read,
read-only, the stores of the projects the user registered, and aggregates at read time; it never copies rows
between stores. Decided 2026-11-06 (roadmap R2).

## Store

`.orchestrator/telemetry/telemetry.db` (WAL, 2 s busy timeout), one per workspace, never shared between
workspaces. `errors.log` beside it holds one line per failure: time, command, error class and message (no input).

| Table | Holds |
|---|---|
| `events` | every accepted event as received (the payload is already whitelisted) |
| `runs` | one row per session: runtime, project, versions, start, end, status, duration, starts |
| `tasks` | task id, the run an agent first worked on it in, title, status, times |
| `agent_invocations` | one row per agent run, including the main session: type, model, status, duration and its source, attempt, parent, error category |
| `usage_records` | tokens per invocation and model, with source, parser version, requests and reason |
| `criteria` | the last result of each ODD criterion; `run_id` stays NULL because an Evidence line doesn't say which session ran the check |
| `ingest_log` | each call's events seen and recorded, elapsed ms (the instrumentation's own overhead) and outcome |
| `claude_pending` | transcripts waiting to be read: invocation, run, path, stop time; deleted once read |
| `schema_migrations` | applied migrations |

Migrations are numbered and applied once, each in its own transaction. A store written by a newer version
(`NewerStore`) is left untouched: the older script records nothing rather than migrating down.

## Criteria from task files

`telemetry.py sync-criteria` (also run at SessionStart and SessionEnd) reads `odd/tasks/*.md` through
`odd_tasks.py`: the *Tasks* table gives `task.*` events, each *Evidence* line `criterion.verified` (date, task,
criterion, result and the method's name, never the command's output). Re-reading the same line is the same event.

## Reports

`telemetry.py usage|metrics [--by agent|model|runtime|project|task|run] [filters]`, `report [<run id>|last]`,
`cost`, `benchmark <dir A> <dir B>`, and the `orchestrator-metrics` skill. `—` means not available, never zero;
coverage says how many finished invocations reported usage; efficiency and cost per task show only with full
coverage; the main session shows apart from agent runs; the benchmark gives no directional reading with fewer than
3 runs a side.

## Settings

| Key | Where | Effect |
|---|---|---|
| `TELEMETRY` | `orchestrator.conf` | `off` records nothing |
| `TELEMETRY_TRANSCRIPTS` | `orchestrator.conf` | `off` reads no transcript: usage is `unavailable` with that reason |
| `TEMPLATE_VERSION` | `orchestrator.conf` | recorded as the run's `orchestrator_version` |
| `ORCH_TELEMETRY_DB` | environment | another store path (tests) |
| `ORCH_RATES` | environment | another rates file (tests) |

## F1 acceptance criteria

The criteria of the Orchestrator 2.0 phase 1 brief (2026-11-03), quoted as given, with the evidence for each.

| Id | Criterion | Evidence | State |
|---|---|---|---|
| F1-01 | Una ejecución genera un run_id único. | `tests/test_telemetry.py › test_each_session_is_its_own_run` | verified |
| F1-02 | Las tareas y agentes quedan relacionados con la ejecución correspondiente. | `tests/test_telemetry.py › test_invocations_belong_to_their_run_and_task` | verified |
| F1-03 | Se registran inicio, finalización y estado. | `tests/test_telemetry.py › test_run_lifecycle` | verified |
| F1-04 | Los tokens se almacenan solamente cuando existe una fuente verificable. | `tests/test_telemetry.py › test_unavailable_usage_is_recorded_with_null_tokens`, `tests/test_telemetry_claude.py › test_unreadable_shapes_are_unavailable` | verified |
| F1-05 | Cada registro de consumo identifica su procedencia. | `tests/test_telemetry.py › test_unavailable_usage_is_recorded_with_null_tokens`, `tests/test_telemetry.py › test_rejects` | verified |
| F1-06 | Los costes API se distinguen de los precios de suscripción. | `tests/test_api_cost.py › test_markdown_is_labelled_an_estimate_and_never_spend` | verified |
| F1-07 | Las métricas se pueden consultar por agente, modelo, runtime y proyecto. | `tests/test_reports.py › test_default_groups_by_agent_and_model`, `tests/test_reports.py › test_filters`, `tests/test_reports.py › test_counted_by_runtime_project_and_run` | verified |
| F1-08 | Los criterios ODD se relacionan con las ejecuciones. | `tests/test_telemetry_criteria.py › test_each_criterion_keeps_its_last_result`, `tests/test_telemetry_criteria.py › test_criteria_link_to_invocations_through_the_task` (through the task; `criteria.run_id` stays NULL by the user's decision of 2026-11-03) | verified |
| F1-09 | Los datos permanecen disponibles después de cerrar la sesión. | `tests/test_telemetry.py › test_data_survives_closing` | verified |
| F1-10 | Los errores de observabilidad no bloquean el desarrollo. | `tests/test_telemetry.py › test_bad_input_is_logged_not_raised`, `tests/test_telemetry.py › test_a_corrupt_database_does_not_block`, `tests/test_telemetry.py › test_no_python_does_not_block` | verified |
| F1-11 | Claude Code y Codex producen registros compatibles con el contrato común. | `tests/test_telemetry_claude.py › test_background_launch_links_the_task_without_storing_the_prompt`, `tests/test_telemetry_claude.py › test_a_killed_session_is_recovered_by_the_next` for Claude Code. Codex not met: no verified hook payloads, Codex not installed | partial |
| F1-12 | Existe un benchmark reproducible. | `tests/test_benchmark.py › test_the_hash_follows_the_request_the_checks_and_the_fixture`, `tests/test_benchmark.py › test_result_json_is_complete_and_holds_no_content`. No valid sample yet (roadmap R6) | verified |
| F1-13 | La instrumentación no genera llamadas adicionales a modelos. | `tests/test_telemetry.py › test_imports_only_local_modules`, `tests/test_reports.py › test_reports_imports`, `tests/test_benchmark.py › test_the_test_guard_stops_run_even_with_a_model` | verified |
| F1-14 | Las instalaciones existentes pueden actualizarse sin perder configuración ni memoria. | `tests/test_update.py › test_keeps_everything_the_user_owns`; run on a real workspace 2026-11-10: memory, task files and the user's changed layer files unchanged (phase 0 task file › Evidence) | verified |
