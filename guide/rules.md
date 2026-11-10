# Project rules

This project's own guidance, read after hat's guide (`<hat>/guide/AGENTS.md`); it wins over any default there.
Written by `hat project add` from what it can detect, then by the orchestrator and the user. hat never writes
inside the project's repos.

## Commands

TODO(hat): per repo, the commands to run, test (and a single test), lint, format and typecheck.

## Repo guides

Conventions for the repos that have no `CLAUDE.md`/`AGENTS.md` of their own. A repo that has one is governed by it, and has no section here.

{{REPO_SECTIONS}}

## How the repos connect

TODO(hat): how the repos depend on each other, where the contract between them is written down, and where the cross-repo decisions live. Delete this section in single-repo mode.

## Rules

Lasting rules agreed with the user for working in this project. The orchestrator adapts to its user: when the user corrects how it works or states a preference that should outlast the session, write it here in the same session, and follow it over any default in hat's guide. A temporary agreement goes to `<state>/memory/DECISIONS.md` with its `Until:`, and a domain or architecture decision goes to the repo's own records.

- none yet
