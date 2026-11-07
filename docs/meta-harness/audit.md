# Audit: the real state of the repository

Date: 2026-11-06 · Base: `main` 60c59b3 (PR #21 merged) · Released: v0.7.0 · Repo: `telmoDev/hat` (renamed from
`telmoDev/orchestrator`; the GitHub redirect keeps the old URLs working for now).

Everything below was checked against the code, the test run and GitHub, not taken from the docs. No model was
called, no code was changed.

## 1. What was checked

| Check | Result |
|---|---|
| `bash tests/smoke.sh` (scaffold, step-4 checks, gate scripts, unit tests) | 39/39 passed, 44 s |
| `python3 -m unittest discover -s tests` (`ORCH_BENCH_NO_MODEL=1`) | 172 tests, OK, 37 s |
| Open PRs on `telmoDev/hat` | none; #9–#21 (all of F1) merged |
| Local branches | 21 (incl. `main`), all merged into `main` (`git branch --no-merged main` is empty): safe to prune when the user wants |
| Local changes | none (clean tree) |
| Workspaces on this machine with the layer | `gfu-sis`, `kaizen`: both `TEMPLATE_VERSION="0.7.0"`, **no telemetry store** (telemetry is unreleased) |
| Runtimes on this machine | Claude Code 2.1.311; **Codex not installed** |
| Spec of the five phases | **not in the repo.** Tests cite criteria F1-01…F1-14 (F1-06, 07, 11, 12 cited by none); F2–F5 have no design document |

## 2. What exists today

The repository is a **workspace scaffolder** (`orchestrator-setup` skill) plus a **local telemetry layer**. It is
not yet a coordinator: nothing in it launches, schedules or supervises a harness. Its parts:

| Area | Files | State |
|---|---|---|
| Scaffold, install, migrate, update | `scripts/scaffold.sh`, `install.sh`, `scripts/migrate.sh`, `scripts/update.{sh,py}` | Implemented and verified (smoke + `test_update.py`, 3 OSes in CI) |
| Shared guide and flow (ODD, TDD, tiers, pre-PR gate) | `templates/AGENTS.md`, `templates/odd/README.md`, `pre-pr-pass.sh`, `push-pr.sh`, `pre-pr-review` | Implemented and verified (smoke) |
| Session memory (Markdown) | `templates/memory/*`, `session-memory.sh`, `decision-index.sh`, `memory-check.py`, `sync-memory` | Implemented and verified; per workspace. Written only when the model runs `sync-memory`: a session closed or killed without it leaves nothing (roadmap S1) |
| Agents | `explorer` (haiku), `architect`, `developer` per repo; `agent-to-codex.py` renders them for Codex | Implemented |
| Telemetry store and contract | `telemetry.py` (event contract v1, SQLite, migrations 1–2, `NewerStore`) | Implemented and verified |
| Claude Code adapter | 6 hooks in `templates/claude/settings.json` → `telemetry.sh` → `telemetry.py hook claude`; `claude_transcript.py` | Implemented and verified offline; live payload check of `SubagentStart`/`PostToolUseFailure` deferred |
| Codex adapter | `templates/codex/hooks.json` has SessionStart only (memory, decisions, update) | **Blocked** (no verified payloads, Codex not installed) |
| Criteria from task files | `odd_tasks.py`, `telemetry.py sync-criteria` | Implemented and verified; `criteria.run_id` always NULL by decision |
| Reports and skill | `reports.py`, `orchestrator-metrics` skill | Implemented and verified |
| API-equivalent cost | `api_cost.py`, `rates.json` (empty) | Implemented; shows nothing until the user adds rates |
| Benchmark | `benchmark/` (B1–B5, hidden checks), `scripts/benchmark.py`, `benchmark_report.py` | Harness verified; **only B1 run, n=1 a side**, and #21 changed every task hash |
| Governance | gate scripts (test-first, attribution, base branch), secret regex in `memory-check.py` | Partial: no permission policy (`permissions` absent from `settings.json`), no budgets, no cross-project policy |

## 3. F1 (Operational Intelligence): the eight points in the brief

| # | Point | Evidence | Verdict |
|---|---|---|---|
| 1 | Main session + subagent metrics | PR #19; `test_telemetry_claude.py` (pending, recovery, killed session); real transcript read offline: 7 requests, 240,156 tokens | Implemented and verified offline. Live hook payload check still open |
| 2 | Idempotency and recovery | `event_id` hashes its identity (replay is a no-op); `test_idempotent_and_a_resumed_session_replaces_its_totals`, `…stays_pending_for_recovery`, `test_a_killed_session_is_recovered_by_the_next`, `test_migrations_are_versioned_and_idempotent` | Verified |
| 3 | No prompts or sensitive content stored | Payload keys whitelisted per event type, strings ≤ 200 chars, `test_background_launch_links_the_task_without_storing_the_prompt`, F1-13 no model/network | Verified for the contract. Not yet audited: `errors.log` content and `transcript_path` in `claude_pending` (a path, kept until read) |
| 4 | No directional reading with < 3 runs a side | PR #20, test in `test_benchmark.py` | Verified |
| 5 | Benchmark PR and tests | #17, #18, #20, #21 merged; macOS job 11 min → 66 s | Verified. Results: only two B1 pilots (n=1), now historical (old hash) |
| 6 | Telemetry docs and contract | Contract lives in the `telemetry.py` docstring, the skill and CHANGELOG | **Pending**: no single contract document (events, statuses, sources, schema, privacy, versioning) |
| 7 | Global vs per-project metrics | One store per workspace; `project_id` column exists; nothing aggregates across workspaces | **Pending**: not defined |
| 8 | Version compatibility and migrations | `schema_migrations`, `NewerStore` (never migrates down), `update.py` (conservative), `test_update.py` | Verified for v0.7.0 → current in tests. Not yet run on a real workspace |

**F1 is not done.** The code is in place and tested, but: (a) no release carries it (v0.7.0 predates it), (b) no
real workspace has produced a single row, (c) the contract has no document, (d) global vs project metrics are
undefined, (e) the benchmark has no valid sample. F1's own purpose, deciding with evidence, is not met yet.

## 4. Feature matrix

States: **V** implemented and verified · **P** partial · **D** designed, not implemented · **—** pending · **N**
not needed (with reason).

| Phase | Functionality | State | Pending work | Depends on |
|---|---|---|---|---|
| F1 | Event contract + SQLite store + migrations | V | Contract document | — |
| F1 | Claude Code adapter (hooks, transcript parser v2, main session) | V (offline) | Live payload check on one real session | F1 release |
| F1 | Codex adapter | — (blocked) | Install Codex, capture real payloads, then adapter | Codex installed |
| F1 | ODD criteria sync | V | — | — |
| F1 | Reports, metrics skill, API-equivalent cost | V | Rates are the user's | — |
| F1 | Workspace updater | V (tests) | First real run (kaizen or gfu-sis) | v0.8.0 |
| F1 | Benchmark harness | V | Valid sample: ≥ 3 runs a side, B2–B5 never run | User's go (spends quota) |
| F1 | Global vs project metrics | — | Decide scope; read-only aggregation | Project registry (X1) |
| F1 | Field data | — | Release v0.8.0, update one workspace, collect 1–2 weeks | v0.8.0 |
| F2 | Code intelligence (index, symbols, impact) | — | Today only the `explorer` agent (haiku) and grep | F1 field data (is exploration where tokens go?) |
| F3 | Agent/model selection by evidence | P | Tiers are static rules in `AGENTS.md`; benchmark compare exists; no history-based selection | F1 data, benchmark n ≥ 3, Codex |
| F4 | Gates (test-first, attribution, base branch, secret regex) | P | Permission policy, budgets, destructive-op policy, cross-project isolation | Project registry |
| F5 | Multi-project coordination | — | Nothing launches or supervises a harness | X1, X2, F4 |
| X | Memory between sessions | P | Model-written only; no automatic capture when `sync-memory` isn't run | — (S1) |
| X | Project/workspace model | P | A workspace is a root with repos; no registry of workspaces | — |
| X | Harness abstraction | P | Two adapters by convention (`.claude/`, `.codex/`), no common contract | — |
| X | Knowledge | P | `memory/` + `DECISIONS.md` + task files per workspace; no OKF, no scopes, no sharing | X1 |
| X | Vector index | N | Excluded by the brief; navigation + grep first | — |
| X | SQLite for memory | N | Discarded 2026-10-15: Markdown stays the source of truth | — |

## 5. Duplicates and inconsistencies found

- **Repo name.** `README.md:38,48` and `INSTALL.md:41` still point to `telmoDev/orchestrator`; the skill is
  `orchestrator-setup`, the clone path `~/orchestrator-setup`, the conf file `orchestrator.conf`, the folder
  `.orchestrator/`. The redirect hides it today; it breaks if another repo ever takes the old name.
- **Two task-id schemes.** Task files use `T<n>`, telemetry `<feature>#T<n>`, tests `F1-xx`: fine, but the F1-xx
  spec that defines them isn't versioned anywhere.
- **`.pyc` files** under `scripts/`, `tests/`, `templates/orchestrator/scripts/` are on disk (ignored, not
  tracked): harmless.
- No duplicated functionality found between scripts.
