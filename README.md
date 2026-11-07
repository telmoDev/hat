# hat

> **Agents:** if a person gave you this link to install it, follow [INSTALL.md](INSTALL.md) step by step.

**hat** is a local-first meta-harness for coding agents: a layer above Claude Code and Codex that organizes how
they work across your repositories, measures what they do and keeps the work recoverable between sessions. It
started as the `orchestrator-setup` skill and is growing into the meta-harness one release at a time; each
release works on its own.

## What it does today

It sets up an **orchestration layer** at the root of a workspace (one or several git repos), for **Claude
Code**, **Codex** or both, on **macOS, Linux and Windows**:

- **One guide for both tools** (`AGENTS.md`): an orchestrator session plans, delegates to agents, verifies and
  reports; it doesn't write application code itself.
- **Agents**: `explorer` (read-only lookups), `architect` (plans and reviews) and one developer agent per repo,
  each run on the cheapest model tier that gets its task right.
- **ODD flow**: *Organic* Driven Development sizes the process to the request (a question gets an answer, a
  small change goes straight through, large work gets a task file in `odd/tasks/`), and *Outcome-Driven*
  Development decides when it is done: criteria verified with evidence, test-first when `TDD` is on.
- **Pre-PR gate**: a checklist and scripts that refuse to push what wasn't reviewed and stamped.
- **Memory between sessions**: `memory/` loads at every start and `sync-memory` keeps it current. A session that
  ends without syncing leaves an automatic handoff of where it stopped (next release).
- **Local telemetry**: runs, agent runs, tokens (with their source), durations and ODD criteria in a SQLite file
  per workspace, with reports and an API-equivalent cost estimate. No network, no model calls, never prompts or
  code ([docs/telemetry.md](docs/telemetry.md); next release).
- **Good-practice defaults that adapt**: design principles, test-first and a quality checklist that hold for any
  stack; setup reads your repos' conventions and asks what to keep, and your corrections become workspace rules.

| Shared by both tools | Claude Code adapter | Codex adapter |
|---|---|---|
| `AGENTS.md` (the guide), `memory/`, `odd/` (task files), `.orchestrator/` (config, checklist, scripts, hooks), `.agents/skills/` | `CLAUDE.md` (imports `AGENTS.md`), `.claude/` (settings, agents, workflow, skill copies) | `.codex/` (config, hooks, agents) |

## Where it is going

The plan is in [docs/meta-harness/roadmap.md](docs/meta-harness/roadmap.md): eight phases, each a release with
an evidence gate, from closing the telemetry phase and measuring a baseline, through a multi-project registry,
a harness capability contract, project knowledge in OKF, governance policies, code and agent intelligence, up to
coordinating approved tasks across projects and harnesses. A feature that claims to save tokens has to beat the
measured baseline, or it stays opt-in. The current state is audited in
[docs/meta-harness/audit.md](docs/meta-harness/audit.md) and the design in
[docs/meta-harness/architecture.md](docs/meta-harness/architecture.md).

## Requirements

- git and the GitHub CLI (`gh`), authenticated.
- bash and Python 3.8+ (3.11+ to validate the Codex TOML files).
- Windows: Git for Windows, whose Git Bash runs the scripts. For Codex, put Git's `bin` folder on `PATH`
  so `bash` resolves from its hooks. Python may be `py -3` or `python`.

## Install

Ask your agent (Claude Code or Codex), in any language:

> Install hat from https://github.com/telmoDev/hat

It follows [INSTALL.md](INSTALL.md): checks your OS and prerequisites, clones the latest release to
`~/orchestrator-setup`, links the skill into every tool you have (a symlink on macOS and Linux, a junction on
Windows), verifies it with `bash install.sh --check`, and explains how to work with it ([USAGE.md](USAGE.md)).

By hand:

```bash
url=https://github.com/telmoDev/hat.git
tag=$(git ls-remote --tags --refs --sort=-v:refname "$url" 'v*' | head -1 | sed 's#.*refs/tags/##')
git clone --branch "$tag" "$url" ~/orchestrator-setup
cd ~/orchestrator-setup
bash install.sh                 # both tools; or --tools claude / --tools codex
bash install.sh --check
```

Then, in a workspace, ask your agent to set it up ("set up the orchestrator here" / "implementa la estructura
de orquestador"): the `orchestrator-setup` skill reads your repos, asks its questions in one message and writes
the layer. The skill, the clone folder and the workspace paths (`.orchestrator/`, `orchestrator.conf`) keep their
names, so existing workspaces need nothing for the rename.

Update by checking out a newer tag (`git fetch --tags && git checkout vX.Y.Z`; read `CHANGELOG.md` first) and then
`bash scripts/update.sh <workspace-root>` for each workspace; remove with `bash install.sh --uninstall`.

## Repository

- `SKILL.md`: what the setup skill does and what it asks before writing.
- `scripts/`: `scaffold.sh` (writes the layer), `update.sh` (brings a workspace to this release),
  `migrate.sh` (from before v0.1.0), `agent-to-codex.py`, `benchmark.py`.
- `templates/`: the files a workspace gets.
- `benchmark/`: fixed tasks with hidden checks to compare flows without trusting a model's word.
- `docs/`: the telemetry contract and the meta-harness plan.
- `tests/`: unit tests and `smoke.sh`, run by CI on the three OSes.

## Versions

Releases follow semver and are listed in [CHANGELOG.md](CHANGELOG.md), each with what an existing workspace
needs to catch up. A workspace records its version in `.orchestrator/orchestrator.conf` › `TEMPLATE_VERSION`.
Maintainers cut a release with `bash release.sh <version>` from a clean `main` (notes come from *Unreleased*).
