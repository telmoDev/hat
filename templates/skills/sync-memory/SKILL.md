---
name: sync-memory
description: Update the orchestrator's session memory in {{ROOT}}/memory/ (PROJECT_STATE, PROGRESS, DECISIONS, NEXT_STEPS) from git and the real files. Use once per session, before it ends, before a break that leaves a task partial, before handing a task to another session, or when the user says "sync memory" / "actualiza la memoria".
---

# Sync the session memory

The memory is the handoff between orchestrator sessions. It is a short index into git and the repos' docs, not a copy of them. Every line must be checked, concise and safe to commit.

The work is split by who can get it right. A script writes what git knows. The orchestrator writes what only this session knows, because it already holds the facts. A second script refuses the result if git contradicts it. Don't use a subagent: briefing one costs more than the edit, and it mislabels features it never saw.

All commands run from the workspace root, `{{ROOT}}`. The repo list is in `.orchestrator/orchestrator.conf`.

## 1. Script: the git-derived state

```bash
bash .orchestrator/scripts/memory-state.sh
```

It rewrites the block between the `state:begin` / `state:end` markers in `memory/PROJECT_STATE.md`: each repo's last commit on its base branch (`BASE_BRANCHES` in `.orchestrator/orchestrator.conf`), every open PR with its draft, review, mergeable and check state, and the *Cleanup* list (worktrees and local branches whose PR is merged or closed). It also stamps the sync date. Never edit that block by hand.

## 2. Orchestrator: the session's judgment

Edit the files directly, with targeted edits. Change only what differs, and keep each file's headings and entry shape.

- **`PROJECT_STATE.md` › In flight**: one row per feature. Each row maps the feature to its ticket (`—` if the project uses none), its spec and decisions, its PRs (`<repo> #N open|draft`) and its outcome status (`2/3 passed, O3 pending`; the criteria text stays in the PR body or the spec). This mapping is the part a script can't know. Every open PR in the generated block must appear in some row. No branch names or commit hashes: the generated block has them. Drop rows whose PRs are all merged or closed. Update **Blocked**.
- **`PROGRESS.md`**: partial tasks only. A task is **done** when its code is on a branch with a PR, the checks ran and passed, and every criterion of its outcome is `passed` on evidence the orchestrator checked: delete its entry, because the PR keeps the record. A task that isn't done gets one entry **at the top**, in the file's shape, with its repo, branch, PR, checks with their real results ("not run" if they weren't run), the integration result, its outcome (the criteria with their status, in full only while no PR body holds them), its cost line (tier, attempts and only the token figures an Agent result reported) and an exact `Continue at:`. A large task's entry instead links its task file with `Doc: odd/tasks/<feature>.md` and leaves the outcome and the cost there; it keeps the branch, checks and `Continue at:` (repo, branch, file(:line) or step, next command). Write "unverified" rather than guess.
- **Task files** (`odd/tasks/*.md`) of the large tasks worked on this session: the task statuses, *Evidence*, *Run log*, *Decisions and scope changes* and the `Next:` line match what happened and what was verified. A task without evidence is not `done`. A finished feature gets `Status: done`. In **In flight**, its *Spec · decisions* cell links the task file.
- **`NEXT_STEPS.md`**: Resume = where each partial task continues. Pending = next tasks in order, without the cleanup the generated block already lists. Waiting on others = only what git can't show (decisions, answers, third parties), with their owner.
- **Something agreed with the user this session**: a lasting rule goes to `AGENTS.md` › *Workspace rules*. A temporary agreement goes to `DECISIONS.md` with an `Until:` (a PR merging, a ticket closing, a question answered, a date). Delete the `DECISIONS.md` entries whose condition has been met.

With `TICKETS` set in the config, check every ticket key you write against that system (the check script can't). Use the right name for each thing: a slice is not its feature, and a PR belongs to the feature whose spec it implements. Link specs and decision numbers. Never paste rules or contracts from the docs. Never write secrets, credentials or personal data. Use tables and IDs, not prose.

## 3. Script: refuse what git contradicts

```bash
python3 .orchestrator/scripts/memory-check.py   # on Windows, `py -3` or `python` if `python3` is missing
```

It fails on any of these:

- a repeated line within a section
- a `#N` that is not a PR in the repo named on its line
- an In flight cell whose `open`/`draft`/`merged` disagrees with GitHub
- an open PR missing from In flight
- a commit hash in In flight
- a `done` entry in `PROGRESS.md`
- a `DECISIONS.md` entry with no `Until:`, or whose `Until:` PR is merged or closed, or whose date has passed
- anything that looks like a secret value or an email address, in the memory or in a task file
- a `Doc:` line in `PROGRESS.md` that names a task file that doesn't exist, or one whose `Status:` is `done`
- in a task file: a task `done` with no *Evidence* line naming it, or `Status: done` with a task not done
- an In flight `N/M passed` cell that its linked task file's *Evidence* contradicts
- an `AGENTS.md` longer than Codex reads (`project_doc_max_bytes` in `.codex/config.toml`); a warning past 85%
- the memory over its word budget (`WORD_BUDGET` in `.orchestrator/orchestrator.conf`): trim `PROGRESS.md` first, then `DECISIONS.md`

Fix every failure and rerun until it passes. Don't commit around it.

## 4. Commit

Skip this step when `.orchestrator/orchestrator.conf` has `ROOT_GIT="no"`: the memory is not versioned. Under hat's global install (the session start says `hat project <id>`), the memory lives in hat's home, a local git repo: run `python3 <hat>/scripts/hat.py commit "sync after <task>"` from the project instead of the commands below.

```bash
git add memory odd && git commit -m "<sync after <task>, in the root's commit convention>"
```

Commit at the root only, following *Workspace rules* (attribution included). Push only if the user set up a remote for the root and asked for it. Never touch anything inside the app repos.

## 5. Report

Tell the user in three lines: what changed in memory, what is partial and where it resumes, and what is blocked.
