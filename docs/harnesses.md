# Harness capability contract

What each runtime can really do for hat, as declared in `templates/orchestrator/scripts/harness.py`
(`tests/test_harness.py` fails when this table and the code disagree). Meta-harness roadmap X2.

- **Declared, not assumed.** A capability is `verified` only when it was checked against the runtime's real
  behaviour; `unverified` when the runtime has it but hat hasn't checked or doesn't use it yet; `unsupported` when
  there is no interface for it. Callers check a capability before relying on it. No forced parity between runtimes.
- **Health check**: `python3 .orchestrator/scripts/harness.py doctor [--json]` says whether each runtime is
  installed (`<cli> --version`) and wired in this workspace (the hooks hat needs), and prints this table. No
  network, no model calls, never starts a session.
- **One module, no base class** until a third runtime needs one.

| Capability | Claude Code | Codex |
|---|---|---|
| `health_check` | verified: `claude --version` and the hooks in `.claude/settings.json` | unverified: `codex --version` and `.codex/hooks.json`; not run against a real install |
| `collect_events` | verified: six hooks into `telemetry.py hook claude` ([telemetry.md](telemetry.md)) | unverified: SessionStart hooks only (memory, decisions, update, handoff); no telemetry until real payloads are verified |
| `usage` | verified: transcript parser `claude-transcript/2`; `unavailable` on any unknown shape | unverified: no verified source, not recorded |
| `execute` | unverified: `claude -p` exists; hat starts no sessions until opt-in dispatch (phase 7) | unverified: `codex exec` exists; same |
| `status` | unsupported: no session status interface; process-level once hat starts runs | unsupported: none known |
| `cancel` | unsupported: no cancel interface; process-level once hat starts runs | unsupported: none known |

A capability moves to `verified` in the PR that checks it, with its evidence (a test on real payloads or a recorded
manual check), and this table changes with it.
