# Design: global install (v0.9.0)

Status: proposal for the user's approval (2026-11-10). Nothing here is built yet.

The user's direction (2026-11-10): hat is installed **once, for every project**, not copied into each one. Today
the skill is global (`~/.claude/skills/orchestrator-setup`) but the layer that does the work is copied into each
workspace: hooks in `.claude/settings.json`, scripts in `.orchestrator/`, `AGENTS.md`, `memory/`, `odd/` and the
telemetry store. Every workspace is updated separately, and every project carries hat's files.

## 1. Goal

- **One install, one update.** Installing hat wires every Claude Code session on the machine; updating it is one
  `git pull` (plus a check), never a per-project run.
- **Repos untouched.** A project carries no hat file. hat's state for a project lives outside it.
- **Per-project state, isolated.** Memory, task files, telemetry and the session handoff stay separate per project,
  as today; only their location moves.
- **Costs nothing where it isn't used.** A session in a folder that isn't a hat project gets no guide, no memory
  and no telemetry rows.
- **Configure, never fork** (roadmap X4). What differs per project is configuration; all projects share one copy
  of the scripts, hooks, agents and guide.

## 2. Layout

```
<clone>/                         the hat repo (code): scripts, hooks, guide, agents, skills. `git pull` updates it.
~/.hat/
  config                         global defaults (shell-style keys, as orchestrator.conf today)
  projects.toml                  registry: id → root, repos, harnesses
  projects/<id>/
    config                       this project's keys (repos, base branches, tiers, TDD, tickets, checklist)
    memory/                      today's <workspace>/memory/
    tasks/                       today's <workspace>/odd/tasks/
    telemetry.db                 today's <workspace>/.orchestrator/telemetry/telemetry.db
    handoff/                     today's <workspace>/.orchestrator/tmp/handoff/
    checklist.md                 only when the project has its own; else the clone's default
~/.claude/
  settings.json                  + hat's hooks, absolute paths into <clone> (merged, never replaced)
  CLAUDE.md                      + one short block: what hat is and where its guide is (≤ ~60 words)
  agents/                        hat's generic agents: explorer, architect, dev (one dev, briefed per repo)
  skills/                        hat's skills (orchestrator-setup is already here)
~/.codex/                        the same, for Codex (section 7)
```

`~/.hat/` holds state only; code stays in the clone, so an update never touches project state and a project's
state never shadows an update.

## 3. A session's lifecycle

1. **SessionStart** (user-level hook, every session): `hat resolve <cwd>` finds the project:
   - the nearest registered root above `cwd` (a workspace with several repos registers its parent folder);
   - otherwise nothing: the hook prints nothing and exits in < 50 ms. Telemetry and handoff do the same.
2. **In a project**, the hook adds to the context, as today's `session-memory.sh` does: the project id, the memory
   (`NEXT_STEPS`, `PROJECT_STATE`), the decision index and a pending handoff draft. It also says where the guide is.
3. **The guide.** Today's `AGENTS.md` (~4,000 words) would cost every session on the machine if it went into
   `~/.claude/CLAUDE.md`. Instead `CLAUDE.md` gets a short pointer, and the SessionStart context of a project
   session carries the guide itself (or its path, if the context limit is too small: G0 decides). Projects pay
   what they pay today; other sessions pay ~60 words.
4. **During and at the end**: the telemetry and handoff hooks are today's, given the project's state directory
   instead of `<workspace>/.orchestrator/`.

## 4. Projects

- **Registering** is one command (`hat project add [<root>]`) or one "yes" when a session in an unregistered git
  repo offers it (decision G-D1). Registering detects what setup asks today (repos, base branches, stack, test
  commands) and writes `~/.hat/projects/<id>/config`; nothing is written into the project.
- **Identity**: `<id>` is the root folder's name plus a short hash of its absolute path (two clones of the same
  repo are two projects). The registry maps id → root; a moved folder is re-pointed with `hat project move`.
- **Isolation** as in architecture §C: each project's stores are separate; the global view (`hat status`,
  `hat metrics`) opens them read-only. Decision R2 holds: every metric belongs to its project's store; the stores
  just live under `~/.hat/projects/`.

## 5. Per-project configuration (X4)

Everything a workspace edits today becomes a key in `projects/<id>/config`, with defaults in `~/.hat/config`:

| Today a workspace forks | Becomes |
|---|---|
| `orchestrator.conf` | `projects/<id>/config` (same keys) |
| `decision-index.sh` paths | `ADR_DIR`, `DECISION_LOG` (already keys) |
| `pre-pr-pass.sh` checklist item number | items looked up by title, not number |
| ticket system inside `sync-memory`, `pre-pr-review` | `TICKETS="none\|jira\|github\|…"` plus `TICKET_PROJECT` |
| `AGENTS.md` *Workspace rules*, repo guides | `projects/<id>/rules.md`, loaded with the memory |
| per-repo `*-dev` agents with a digest | one `dev` agent; the brief names the repo, its guide and its standards |

## 6. Agents and skills

Claude Code loads agents from `~/.claude/agents/` for every project, so hat ships **generic** agents: `explorer`,
`architect`, `dev`. What made `backend-dev` / `frontend-dev` specific (the repo, its guide, its standards digest)
moves into the brief, which already carries the repo, criteria and contract. Model tiers stay per brief. Project
agents a repo keeps in its own `.claude/agents/` keep working; hat never writes there.

## 7. Codex

Codex reads a global `~/.codex/AGENTS.md` and `~/.codex/config.toml`. Whether it runs user-level hooks with a
`cwd` in the payload is **unverified** (Codex isn't installed here; telemetry decision: no invented fields). Until
verified: the pointer goes into `~/.codex/AGENTS.md`, project state is read by the orchestrator on demand
(`hat context`), and Codex records no telemetry, as today.

## 8. Existing workspaces

- **Coexistence.** A workspace with the per-project layer (`.orchestrator/` present) keeps working. The global
  hooks skip any session whose project still has its own layer, so nothing runs twice.
- **Migration** (`hat migrate <workspace>`, on the user's yes): registers the project, moves `memory/`,
  `odd/tasks/`, the telemetry store and the handoff state into `~/.hat/projects/<id>/`, turns the conf and the
  forked files into config keys (§5), and lists the layer files the workspace can then delete. It never deletes
  them itself and never commits. A dry run first, like `update.sh`.

## 9. What changes in earlier decisions

| Decision | Was | Becomes |
|---|---|---|
| D5 global location | `~/.hat/`, opt-in, read-only on projects | `~/.hat/` **is** the install; still read-only on project files |
| R2 metrics scope | one store per project, in the project | one store per project, under `~/.hat/projects/<id>/` |
| Architecture §C | a project is a workspace with its own `.orchestrator/` | a project is a registered root; hat state lives outside it |
| Phase order | global layer in phase 2 (v0.9.0) after the baseline | global install is the next phase (v0.9.0); the baseline is gathered on it |

## 10. Decisions for the user

| # | Question | Recommendation |
|---|---|---|
| G-D1 | Where hat is active | registered projects only; in an unregistered git repo, one line at start offers to register it (≈ 20 tokens) |
| G-D2 | Memory versioned? Today it is committed in the workspace root's git | `~/.hat/` as a local git repo, one commit per `sync-memory` (history kept, no remote unless the user adds one) |
| G-D3 | A multi-repo workspace | its parent folder is the project root, as today; a single repo is its own root |
| G-D4 | Migrating existing workspaces | one at a time, on the user's yes; the per-project layer stays supported through v0.9.x |

## 11. Plan

| ID | Task | Size | Depends on |
|---|---|---|---|
| G0 | Spike, no code shipped: in a live Claude Code session, verify that user-level hooks run alongside project hooks, that every payload carries `cwd`, the SessionStart context size limit, and `@` imports in `~/.claude/CLAUDE.md` | S | — |
| G1 | `~/.hat/` home, registry and `hat resolve`; `hat project add/list/move` | M | G0 |
| G2 | State directory: telemetry, handoff, memory-state, sync-memory and memory-check take the project's state dir instead of `<workspace>/` | M | G1 |
| G3 | Global wiring: `install.sh --global` merges hooks into `~/.claude/settings.json`, adds the `CLAUDE.md` pointer, links agents and skills; `--uninstall` removes exactly what it added | M | G1 |
| G4 | Guide split: a project-agnostic guide in the clone, project rules in `projects/<id>/rules.md`, the generic `dev` agent | M | G0 |
| G5 | Config instead of forks (X4): `TICKETS`, checklist items by title, the keys of §5 | M | G4 |
| G6 | `hat migrate` (dry run, move, report) and coexistence with per-project layers | M | G2 G3 |
| G7 | `hat doctor` and `hat status` across registered projects (read-only) | S | G1 |

Exit gate for v0.9.0: one machine with the global install and no per-project layer; two projects registered, each
with its own memory, tasks and telemetry, shown apart by `hat status`; a session outside any project gets no hat
context and writes no rows; a migrated workspace keeps its memory, tasks and telemetry history; an update is one
`git pull` and touches no project state; tests on 3 OSes.

## 12. Tokens

- Outside a project: ~60 words of `CLAUDE.md` pointer per session, nothing else.
- In a project: the same as today (guide + memory at start, cached after the first turn), minus the per-repo
  agent digests now carried by the brief only when a task needs them.
- Migration and setup: deterministic scripts, no model calls.
