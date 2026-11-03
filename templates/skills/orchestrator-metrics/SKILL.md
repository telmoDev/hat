---
name: orchestrator-metrics
description: Show the orchestrator's local telemetry for this workspace (agent runs, tokens, durations, coverage, ODD criteria, API-equivalent estimate) from {{ROOT}}/.orchestrator/telemetry/telemetry.db, with no model calls. Use when the user asks how much a run, task, agent or model consumed, how runs performed, or "metrics" / "consumo" / "cuánto gastó".
---

# Orchestrator metrics

The telemetry hooks record every session (a run), every agent run and its reported usage, and the ODD criteria
from the task files, into a local SQLite store. Reports are read from it by a script: no model call computes them.

Cheapest: the user runs the command, so the report costs no tokens. Suggest it in one line, for example
`! python3 .orchestrator/scripts/telemetry.py metrics --by task`, and stop. If you run it, paste its output as it
is: don't recompute, round, estimate or fill in a `—`, and don't drop its notes.

| Question | Command (from `{{ROOT}}`) |
|---|---|
| What did the last session do and use? | `python3 .orchestrator/scripts/telemetry.py report` (or `report <run id>`) |
| Tokens by agent, model, task, run, project or runtime | `python3 .orchestrator/scripts/telemetry.py usage --by <dimension>` |
| Performance, quality and efficiency, and the instrumentation's overhead | `python3 .orchestrator/scripts/telemetry.py metrics --by <dimension>` |
| What would this usage cost through the API? | `python3 .orchestrator/scripts/telemetry.py cost` |

Filters for `usage` and `metrics`: `--project`, `--runtime`, `--model`, `--agent`, `--task` (`<feature>#T<n>`),
`--status`, `--since`, `--until` (a date or an ISO time, UTC).

How to read them:

- `—` means not available, never zero. Coverage says how many finished agent runs reported usage.
- Efficiency and cost per task show only when every task in the row is fully covered; otherwise "incomplete".
- "Succeeded" means finished without a runtime error, not that the work is right: the criteria say that.
- Criteria come from the task files and are not attributed to runs. A task without criteria hasn't failed.
- The API-equivalent figure is an estimate at the rates in `.orchestrator/rates.json` (empty until the user adds
  them), never what a subscription costs.
- Codex runs aren't recorded yet: its adapter waits for verified hook payloads.
