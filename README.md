# hat

**Harness Augmentation & Orchestration Toolkit**

> **Agents:** if a person gave you this link to install it, follow [INSTALL.md](INSTALL.md) step by step.

An intelligent, extensible layer that enhances AI coding harnesses, complementing their native capabilities with
persistent memory, work direction, coordination, observability and governance.

**It doesn't replace the harness. It makes it work better.**

hat is local-first and works with the harnesses you already use (Claude Code today, Codex in part). It started
as the `orchestrator-setup` skill and grows one release at a time; each release works on its own, and *What it
does today* says which parts exist now.

## What it does today

hat is **installed once and works in every project you register**, for **Claude Code** (Codex: partly, see
below), on **macOS, Linux and Windows**. Your repositories carry no hat file: each project's state lives in
`~/.hat/projects/<id>/`.

- **One install, one update.** `bash install.sh --global` adds hat's hooks to `~/.claude/settings.json`, its
  agents and two skills, and a short note to `~/.claude/CLAUDE.md`; it keeps every setting of yours and
  `--uninstall` removes exactly what it added. Updating is a `git pull` of the clone.
- **Projects, apart.** `hat.py project add` registers a project (a repo, or the folder that holds several).
  Its memory, task files, config, own rules, telemetry and session handoff live in `~/.hat/projects/<id>/`,
  a local git repo, so its history is kept. Outside a registered project hat adds nothing to a session.
- **A session knows where it is.** At start, a short header names the project and points to hat's guide and the
  project's rules, followed by its memory and its binding decisions.
- **The ODD flow.** An orchestrator session plans, delegates to agents (`hat-explorer`, `hat-architect`,
  `hat-dev`, each on the cheapest model tier that gets its task right), verifies and reports; it doesn't write
  application code. *Organic* Driven Development sizes the process to the request; *Outcome-Driven*
  Development decides when it is done: criteria verified with evidence, test-first when `TDD` is on. A pre-PR
  gate refuses to push what wasn't reviewed and stamped.
- **Nothing lost between sessions.** `sync-memory` keeps the memory current; a session that ends without it
  leaves a handoff of where it stopped; a compaction saves where the session was and shows it right after.
- **Local telemetry.** Runs, agent runs, tokens (with their source), durations, compactions and ODD criteria in
  SQLite per project, with reports and an API-equivalent cost estimate. No network, no model calls, never
  prompts or code ([docs/telemetry.md](docs/telemetry.md)).
- **Configure, never fork.** What differs per project (tickets, checklist, decision records) is configuration,
  so every project shares one copy of hat.

| Command (from the clone, `python3 scripts/hat.py …`) | What it does |
|---|---|
| `project add [<root>]`, `project list`, `project move`, `project remove` | register and manage projects |
| `status` | every project apart: its resume point, active tasks, last session |
| `doctor` | is hat installed and healthy on this machine |
| `migrate <workspace> [--dry-run]`, then `--cleanup` | move a workspace set up the per-project way to the global install, saving its own rules verbatim first |
| `commit <message>` | record the current project's memory and tasks in hat's home |

**The per-project layer** (the `orchestrator-setup` skill writing `AGENTS.md`, `.orchestrator/`, `memory/`
into a workspace) still works through v0.9.x; the global hooks leave such a workspace alone, and offer at
session start to migrate it. **Codex** reads the note in `~/.codex/AGENTS.md`; its hooks and telemetry wait for
verified payloads.

## Where it is going

The plan is in [docs/meta-harness/roadmap.md](docs/meta-harness/roadmap.md): phases that each end in a release
with an evidence gate. Done: the telemetry phase (v0.8.0) and the global install (v0.9.0,
[design](docs/meta-harness/global-install.md)). Next: a measured baseline of where tokens go, then a harness
capability contract, project knowledge in OKF, governance policies, code and agent intelligence, up to
coordinating approved tasks across projects and harnesses. A feature that claims to save tokens has to beat the
measured baseline, or it stays opt-in.

## Requirements

- git and the GitHub CLI (`gh`), authenticated.
- bash and Python 3.8+ (3.11+ to validate the Codex TOML files).
- Windows: Git for Windows, whose Git Bash runs the scripts. For Codex, put Git's `bin` folder on `PATH`
  so `bash` resolves from its hooks. Python may be `py -3` or `python`.

## Install

Ask your agent (Claude Code or Codex), in any language:

> Install hat from https://github.com/telmoDev/hat

It follows [INSTALL.md](INSTALL.md): checks your OS and prerequisites, clones the latest release to
`~/orchestrator-setup`, installs hat for every project (after telling you what it changes), verifies it, and
explains how to work with it ([USAGE.md](USAGE.md)).

By hand:

```bash
url=https://github.com/telmoDev/hat.git
tag=$(git ls-remote --tags --refs --sort=-v:refname "$url" 'v*' | head -1 | sed 's#.*refs/tags/##')
git clone --branch "$tag" "$url" ~/orchestrator-setup
cd ~/orchestrator-setup
bash install.sh --global          # hooks, agents, skills and a note in ~/.claude, for every project
python3 scripts/hat.py doctor     # everything ok?
cd <your project> && python3 ~/orchestrator-setup/scripts/hat.py project add
```

A workspace you set up the per-project way: `python3 ~/orchestrator-setup/scripts/hat.py migrate <workspace>
--dry-run`, then without `--dry-run`, review `rules.md` with your agent, then `--cleanup` (one commit, git can
undo it).

Another Claude Code account on the same machine (an alias with its own `CLAUDE_CONFIG_DIR`, e.g.
`~/.claude-work`): `CLAUDE_CONFIG_DIR=~/.claude-work bash install.sh --global` wires it too. Both accounts use the
same clone and the same `~/.hat`: one hat, the same projects, memory and telemetry; each account keeps its own quota.

Update: `git fetch --tags && git checkout vX.Y.Z` in the clone (read `CHANGELOG.md` first), then
`bash install.sh --global` again. Remove: `bash install.sh --global --uninstall` (projects' state stays in
`~/.hat`).

## Repository

- `SKILL.md`: what the setup skill does and what it asks before writing.
- `scripts/`: `hat.py` (projects, status, doctor, migrate), `hat_install.py` (the global install),
  `hat-hook.sh` (the one entry of the global hooks), `build_guide.py`; for the per-project layer `scaffold.sh`,
  `update.sh`, `migrate.sh`, `agent-to-codex.py`; `benchmark.py`.
- `guide/`: what every project shares under the global install: the guide, the rules template, the agents and
  skills, built from `templates/` by `build_guide.py`.
- `templates/`: the per-project layer, and the scripts and hooks both installs run.
- `benchmark/`: fixed tasks with hidden checks to compare flows without trusting a model's word.
- `docs/`: the telemetry contract and the meta-harness plan.
- `tests/`: unit tests and `smoke.sh`, run by CI on the three OSes.

## Versions

Releases follow semver and are listed in [CHANGELOG.md](CHANGELOG.md), each with what an existing install or
workspace needs to catch up.
Maintainers cut a release with `bash release.sh <version>` from a clean `main` (notes come from *Unreleased*).
