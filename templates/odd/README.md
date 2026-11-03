# Task files

One file per large feature, `odd/tasks/<feature>.md` (*Organic Driven Development* in `AGENTS.md`). It is the feature's source of truth: what was asked, what "done" means, which tasks remain and the evidence of each. Written before any code changes, and kept up to date as the work goes. A small task has none: its outcome lives in the brief and the PR body.

Rules:

- **Only the orchestrator writes it.** Agents read their task in it and report; the orchestrator records.
- **The request is quoted, never paraphrased.** The user's words go in *Request* exactly as given. A later addition or change of scope is quoted too, with its date, and logged under *Decisions and scope changes*. Briefs copy criteria from here word for word.
- **A task is `done` only with evidence**: its criteria rerun by the orchestrator and logged under *Evidence* with the real result. Code written or a test attempted is not evidence. A criterion that couldn't be verified stays `pending`.
- **Figures are reported, never estimated.** The *Run log* takes the tokens and duration the tool reported, or `not reported`.
- **Links, not copies.** When the repo keeps specs or decision records, link them. `memory/` links to this file and never copies it.
- The local telemetry reads the *Tasks* table and the *Evidence* lines (criterion, result and date only, never the command or its output) to relate criteria to the agents that worked on each task. It never writes here.
- `memory-check.py` holds these files to their rules: no secrets or personal data, no task `done` without an *Evidence* line naming it, no `Status: done` while a task isn't, and the *In flight* cell `N/M passed` in `memory/PROJECT_STATE.md` must match the *Evidence* (each criterion's last result). Keep the shapes below so it can read them.
- When the feature is done (every task `done`, its PRs merged), set `Status: done`. The file stays as the record.

Shape:

```
# <feature>

Status: active | paused | done · Next: T<n> <what comes next>
Ticket: <id or —> · Repos: <repos> · PRs: <repo #N open|draft|merged>

## Request
> <the user's request, quoted exactly>
> <YYYY-MM-DD: a later addition, quoted exactly>

## Outcome
Goal: <what the user asked for, in their terms>
Outcome: <the observable result when this is done>
Criteria: O1 <verifiable by a test, a command or a demo> · O2 …
Constraints: <scope limits, decisions it must respect, what is out of scope>
Assumptions · risks · depends on: <only when there are any>

## Specs
- S1 <what must hold> — criteria O1, O2 — check: <test or command>

## Tasks
| ID | Task | Serves | Depends on | Agent · tier | Status |
|---|---|---|---|---|---|
| T1 | <what> | S1 · O1 | — | <agent> · <tier> | pending |
Status: pending | in progress | blocked (why) | done (only with evidence below)

## Evidence
- YYYY-MM-DD T1 · O1 · `<test or command>` → passed|failed: <the line that shows it>
- YYYY-MM-DD T1 · TDD skipped: <why no deterministic test fits> · checked with `<command or demo>`

## Run log
- YYYY-MM-DD T1 · <agent> · <tier> · attempt <n> · tokens <reported | not reported> · duration <reported | not reported> · <result> · <first error line or —>

## Decisions and scope changes
- YYYY-MM-DD <what changed, why, who decided>
```
