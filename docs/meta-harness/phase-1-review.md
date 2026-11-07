# Phase 1 review (R3)

Date: 2026-11-06 · Base: `main` after PR #25 · Claude Code 2.1.311 · No model was called.

The review the user asked for before releasing F1 (v0.8.0): privacy, hook latency, failure isolation, and the
update path from v0.7.0. Every figure below comes from a command that ran; the scratch workspaces were thrown away.

## Method

- **Latency and concurrency**: a workspace scaffolded from the current templates; each Claude Code hook run 20
  times through `.orchestrator/hooks/telemetry.sh` with synthetic payloads, timed end to end (bash + Python start +
  work). Transcripts: the largest real ones on this machine (main session 41 MB, subagent 14.5 MB), read for
  figures only. Then 8 `SubagentStop` hooks of one session at once.
- **Privacy**: a brief with a body after its header, an invalid hook input, an event with an unknown payload key,
  an unreadable transcript path; then the store and `errors.log` were searched for any of it.
- **Update path**: copies of the two real workspaces' orchestration layers (`kaizen`, `gfu-sis`, both v0.7.0,
  heavily customized), committed, then `scripts/update.sh --dev --dry-run` and `--dev`; then the hooks,
  `telemetry.py report`, `sync-criteria` and the workspace's own `memory-check.py` on the result. The real
  workspaces were only read.

## Results

| Check | Result |
|---|---|
| Hook latency, p95 (SessionStart, SubagentStart, PostToolUse, SubagentStop) | 34–38 ms (max 44 ms) |
| SessionEnd, p95 (reads a 14.5 MB subagent transcript) | 67 ms |
| SessionEnd reading a 41 MB main transcript | 143 ms p50, 147 ms max (5 runs) |
| In-process time (`ingest_log`), p95 | 46 ms; 0 failed calls |
| 8 subagents stopping at once | all 8 recorded with usage; slowest hook 40 ms; no lock errors |
| Transcript parser `claude-transcript/2` on current transcripts | reads 2.1.292, 2.1.308 and this session's 2.1.311 transcript (112 requests) |
| Prompt body after the brief header stored | no |
| Transcript paths stored in `events` | no (only in `claude_pending` until read) |
| Update on `kaizen` copy | exit 0; user files (`AGENTS.md`, `CLAUDE.md`, `memory/`, `odd/`, checklist) unchanged; conf only gained keys; 8 hooks added; 5 scripts/skills the user changed kept, with `.new` copies |
| Update on `gfu-sis` copy | exit 0; same; 6 `.new` copies |
| After the update | hooks record runs; `sync-criteria` reads the real task files (kaizen 10 tasks, 16 criteria; gfu-sis 31 tasks, 43 criteria); the workspace's own `memory-check.py`: 0 errors |

All within target (hook p95 < 100 ms). Nothing blocked a session; nothing printed.

## Findings

| # | Finding | Severity | Decision |
|---|---|---|---|
| F1 | `errors.log` quotes an unknown payload key verbatim. Through the hooks keys are ours, but `telemetry.py ingest` takes external input, and a key can carry text (seen: `payload key 'prompt text here: hunter2' …`). | low (local file, `ingest` only) | **fix**: quote a key only when it looks like an identifier |
| F2 | The session handoff lists every active task file, not the ones the session worked on. On the `gfu-sis` copy, 10 lines of features other sessions own, which `memory/` already tracks. | medium (noise in context) | **fix**: list task files changed since the session started; count the others in one line |
| F3 | `update.py` doesn't touch `.codex/hooks.json`: Codex workspaces add the handoff hook by hand (CHANGELOG *Workspaces*). | low | accepted for v0.8.0; revisit with the Codex adapter (A2) |
| F4 | Customized workspaces get several `.new` copies to merge by hand (5 and 6 on the real ones). | expected | accepted: R4 merges them with the user, workspace by workspace |
| F5 | A main transcript unreadable at its session end stays queued until the next session starts (by design: the last attempt). | none | accepted |
| F6 | `errors.log` lines can hold a local path (an unreadable transcript's `OSError`). | none (local, the user's own paths) | accepted |

## Global vs project metrics (R2)

Decided with the plan (roadmap R2) and recorded in [docs/telemetry.md](../telemetry.md) › *Scope*: every metric
lives in its project's store; there is no global store. A later global view (phase 2) only reads the stores of
projects the user registered, read-only.

## Verdict

F1 is ready to release once F1 and F2 are fixed. Still open after that, by plan: F1-11 (Codex) and F1-14 on a real
workspace (R4), and a valid benchmark sample (R6).
