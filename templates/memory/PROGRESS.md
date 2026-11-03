# Progress

Partial tasks only, newest first, written by `sync-memory`. A task leaves this file when it is done: its PR and the git history of `memory/` keep the record.

Entry shape:
```
## YYYY-MM-DD — <task> (<ticket or —>) — partial
Doc: odd/tasks/<feature>.md   (large task: its outcome, evidence and run log live there, so leave out Outcome and Attempts)
Spec: <spec file> · <decision ids>
<repo>: <branch> / PR #n — <files or "none">   (one line per repo)
Outcome: O1 <criterion> — passed|failed|blocked|pending (<test or command>) · O2 …   (small task; full text only until a PR body holds it)
Checks: <each check with its real result, or "not run">
Attempts: <task-n> · <agent> · tier <tier> · attempt <n> · <result> · <first error or —>   (small task; tokens and duration: `telemetry.py report`)
Integration: <what was exercised end to end, result | not run>
Continue at: <repo, branch, file:line or step, next command>
```
