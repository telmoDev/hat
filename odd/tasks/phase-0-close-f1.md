# phase-0-close-f1

Status: active · Next: T2 S1 session handoff
Ticket: — · Repos: hat · PRs: hat #22 open (plan) · #23 open (T1) · #24 open (Organic + Outcome wording)

## Request
> tambien hay que implementar memoria entre sessions
> (chosen gap: "Captura automática")
> bueno como ves vamos a crear un meta-harness, asi que hay que planificar bien las fases para implementar cada cosa como corresponda
> este template de orquestador lo vamos a tranformar a meta-herness y vamos a usar y mejorar este repo para llegar al meta-herness
> asi que hay mucho trabajo pero vamos de poco a poco
> 2026-11-06: sí, haz commit, abre el PR y arranca con R1 y S1

## Outcome
Goal: close F1 (Operational Intelligence) and add automatic session handoff, as phase 0 of the meta-harness.
Outcome: v0.8.0 released with a documented telemetry contract and automatic session handoff, running on one real workspace.
Criteria: O1 every event type and key in `telemetry.py` is in `docs/telemetry.md`, checked by a test · O2 every
F1-xx criterion is traceable to a test or a recorded manual check · O3 an unsynced session leaves a handoff draft
shown at the next start, nothing after a synced one, a killed session recovered (S1 O1–O5 in the roadmap) ·
O4 phase-1 review findings fixed or accepted, tests green on 3 OSes · O5 v0.8.0 released and one workspace
updated with its user files unchanged and a live session recorded.
Constraints: no model calls in code or tests; no network in hooks; Markdown memory written only by the
orchestrator; merges and releases are the user's; one push authorization per feature.
Assumptions · risks · depends on: D1 and D9 before T5 (R4); the workspace for T5 is the user's pick.

## Specs
- S1 The contract doc matches the code — O1, O2 — check: `tests/test_telemetry_doc.py`
- S2 Session handoff — O3 — check: `tests/test_session_handoff.py`, smoke

## Tasks
| ID | Task | Serves | Depends on | Agent · tier | Status |
|---|---|---|---|---|---|
| T1 | R1 contract doc + F1 spec traceability | S1 · O1 O2 | — | orchestrator · normal | done |
| T2 | S1 automatic session handoff | S2 · O3 | — | orchestrator · normal | in progress |
| T3 | R2 global vs project metrics decision | O1 | T1 | orchestrator · trivial | pending |
| T4 | R3 phase-1 review + X3 rename | O4 | T1 | architect · normal | pending |
| T5 | R4 release v0.8.0, update one workspace | O5 | T2 T3 T4, D1 D9 | user + orchestrator | pending |

## Evidence
- 2026-11-06 T1 · O1 · `python3 -m unittest tests.test_telemetry_doc` → passed: 6 tests OK (red before the doc; removing one key from the doc fails it)
- 2026-11-06 T1 · O2 · `python3 -m unittest tests.test_telemetry_doc` → passed: 14 criteria traced (F1-11, F1-14 partial)

## Run log
- 2026-11-06 T1 · orchestrator · normal · attempt 1 · PR #23 open · — · —

## Decisions and scope changes
- 2026-11-06 Plan in `docs/meta-harness/roadmap.md` (phases 0–7). The original F1-01…F1-14 texts were found in the
  2026-11-03 session (the user's Orchestrator 2.0 brief) and go into `docs/telemetry.md`.
- 2026-11-06 Push authorized by the user for the plan PR; R1 and S1 get their own PRs.
- 2026-11-06 The user: Organic and Outcome-Driven Development complement each other; keep both. Wording in PR #24.
- 2026-11-06 Push authorized by the user for R1 (#23) and the wording PR (#24).
