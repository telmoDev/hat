---
name: orchestrator-setup
description: Set up the orchestrator layer in a multi-repo workspace, for Claude Code, Codex or both, on macOS, Linux or Windows ("implementa la estructura de orquestador"): shared AGENTS.md guide, memory/ + sync-memory, explorer/architect/dev agents, Organic Driven Development (ODD) flow with verified outcomes, task files and run log, test-first (TDD), model tiers by task size, pre-PR gate, token-saving settings. Ships good-practice defaults for any stack and adapts them to the user's repos and preferences.
---

# Set up the orchestrator structure

This sets up an orchestration layer at the root of a workspace whose application repos sit side by side
underneath it. The orchestrator plans, delegates, integrates and reports. Subagents write the application
code. One guide, `AGENTS.md`, serves both tools: Codex reads it directly and Claude Code through a
`CLAUDE.md` that imports it. Everything shared lives in `.orchestrator/` (config, checklist, scripts,
hooks), `.agents/skills/`, `memory/` and the task files in `odd/`; `.claude/` and `.codex/` hold only each tool's adapter.

The orchestrator brings its own way of working: an organic flow (ODD) whose process grows only as far as the
request needs, verified outcomes, test-first, design principles and
patterns, and a quality checklist. These defaults hold for any stack. Everything else is the user's: the
stack, the commit and PR conventions, the ticket system, attribution. Setup reads those from the repos and asks
about the rest, and the user keeps, rewrites or drops any default. After setup, the guide keeps adapting:
corrections and preferences the user states become *Workspace rules*.

The scaffold and the templates are in this skill's directory (`scripts/`, `templates/`). It copies them
and **never overwrites an existing file**: it reports `skip` instead. It is safe to run again. It runs on
macOS, Linux and Windows: on Windows, in Git Bash (Git for Windows), with Python 3 as `python3`, `python`
or `py -3`. It creates no symlinks.

## 1. Find the workspace and its repos

- The target is the directory the user names. If they name none, use the current working directory.
  If that directory is itself a repo inside a workspace, ask whether they meant its parent.
- Repos are the immediate subdirectories that contain `.git`. If there are none, the root itself is
  the only repo (single-repo mode, which the script detects).
- For each repo, read its `AGENTS.md`/`CLAUDE.md`/`README` if it has them, and always its manifest
  (`package.json`, `composer.json`, `pyproject.toml`, `go.mod`…) and its lint/test config. From these,
  get the stack and the commands for test, lint, format and typecheck. Many repos have no guide and no
  skills of their own. That's normal: their conventions get written at the root (step 3).
  Ask the user only for what you can't find there.
- A repo directory whose name has whitespace is refused: ask the user to rename it. Other names are
  fine: the developer agent's name is the repo name slugged (`My.API` → `my-api-dev`; `my_api_dev` in Codex).
- Read each repo's conventions from its history: `git -C <repo> log --format=%s -30` for commit subjects, and
  `gh pr list --state merged -L 20 --json title` for PR titles. Note the convention they follow (Conventional
  Commits, ticket prefixes, free text) and whether commits carry AI attribution.
- Note which repos have CI (`.github/workflows/`, `.gitlab-ci.yml`…) and what it runs: the full suite
  stays out of local checks there.

### Ask, in one message

Don't ask the choices one by one. Show the user, in one message, what you found (repos, stacks, conventions,
CI) and the table below with the defaults filled in from what the repos show, and ask which to change and
whether they have standards of their own to add. Versioning has no default: ask it on its own line in the
same message. A reply that accepts the table accepts each line as written.

| Choice | Default | Goes to |
|---|---|---|
| Tools that run the orchestrator | Claude Code and Codex | `--tools` |
| Codex model per tier (with Codex; check `/model` in Codex) | trivial `gpt-6-luna`, normal `gpt-6.1-sol`, hard `gpt-6-astra` | `CODEX_TRIVIAL`, `CODEX_NORMAL`, `CODEX_HARD` in the environment |
| Commit and PR convention, AI attribution | what the history shows; with no convention, Conventional Commits, titles of at most 72 characters, branches `<type>/<topic>` | the repo's section under *Repo guides* |
| `push-pr.sh` enforces the title and refuses AI attribution | match the history | `TITLE_PATTERN`, `TITLE_MAX`, `ATTRIBUTION="refuse"` |
| Ticket system (Jira, Linear, GitHub Issues…) | none | step 3, *Tickets* |
| The orchestrator's standards (`software-principles`, `design-patterns`) and the checklist's quality items (part C) | keep all; their own standards are skills, in `.agents/skills/` with a row in *Standards* | step 3 |
| Test-first enforced | `TDD="strict"`, with the commit subjects of the history; repos with no test runner left out of `TDD_REPOS` | `orchestrator.conf` |
| `pre-pr-review` for large tasks (2–3 `architect` reviewers plus one verifier per finding) | yes | `AGENTS.md` records the opt-in with the date; no: step 3, *Review declined* |
| Notice when an orchestrator update is out (SessionStart, looked up in the background once a day) | yes | no: `--no-update-check` |
| Plugins and MCP servers this workspace doesn't need (with Claude Code) | none | `.claude/settings.json` › `enabledPlugins` (`"<plugin>@<marketplace>": false`) |
| Version the orchestration layer in git | **no default: always ask** | `--git` or `--no-git`; the scaffold refuses to run without one |

Notes for the table:

- **Test-first.** With `TDD="strict"`, `pre-pr-pass.sh` refuses a code commit with no test commit before it.
  `TDD_TEST_COMMIT` and `TDD_CODE_COMMIT` tell the two apart by subject; their defaults read Conventional
  Commits (`test…`, `feat…`/`fix…`), so match them to the history. `off` disables the check everywhere.
- **`pre-pr-review`.** Claude Code's Workflow tool needs the opt-in in the user's words: the table's line must
  name it, and the reply must accept it, on its own or with the whole table.
- **Conventions.** When a repo shows no convention and the user takes the default, write it in the repo's
  section under *Repo guides*, and set `TITLE_PATTERN`/`TITLE_MAX` only if the user wants it enforced.

## 2. Run the scaffold

```bash
bash <this skill's directory>/scripts/scaffold.sh --git|--no-git [--no-update-check] [--tools claude,codex] <workspace-root> [repo ...]
```

With no repo arguments it uses the detected ones. It creates:

| Path | Tool | What it is |
|---|---|---|
| `AGENTS.md` | both | The guide: orchestrator role, the ODD flow (a question changes nothing; size by understanding, risk and how easily the work resumes; a task file for a large task; resume from evidence, not ticks; one push authorization per feature), Outcome-Driven Development alongside it (Organic sets how much process, Outcome-driven when it is done: outcome and criteria before delegating, test-first when `TDD` is on, the orchestrator verifies each criterion as `passed`/`failed`/`blocked`/`pending`), *Standards* (the skills briefs name), token budget with *Model tiers* (Claude and Codex models per tier; escalate one tier after two failures), *Repo guides* for repos with no guide of their own, *Workspace rules* (where the user's corrections and preferences go), and *Tool mapping*: what differs between the two tools, and the platform rules. Created only if absent; otherwise the template goes to `.orchestrator/AGENTS.orchestrator.md` for you to merge |
| `memory/*.md` | both | The four memory files, empty and in their entry shape |
| `odd/README.md` | both | The shape and rules of a large task's file, `odd/tasks/<feature>.md`: the request quoted exactly, outcome, specs, tasks T1… with dependencies and status, evidence, run log (tokens and duration as reported), decisions and scope changes |
| `.orchestrator/orchestrator.conf` | both | `REPOS`, `BASE_BRANCHES` (from `origin/HEAD`, else `main`, else `master`; `TODO` when none), `WORD_BUDGET`, `TDD`, `TDD_TEST_COMMIT`, `TDD_CODE_COMMIT`, `TDD_REPOS`, `TDD_SINCE`, `CODEX_ONLY_SKILLS`, `TELEMETRY`, `TELEMETRY_TRANSCRIPTS`; optional `GIT_WRAPPER`, `TICKET_LINE`, `TITLE_PATTERN`, `TITLE_MAX`, `ATTRIBUTION`, `ADR_DIR`, `DECISION_LOG`, `UPDATE_CHECK` |
| `.orchestrator/rates.json` | both | API rates for `telemetry.py cost`, empty: the user adds the provider's published prices with their date and source. The estimate is API-equivalent, never a subscription's spend |
| `.orchestrator/pre-pr-checklist.md` | both | The pre-PR gate: part A mechanical (owning agent), part B the flow's review, part C quality (defaults the user adapts). Grows one line per review comment it missed |
| `.orchestrator/scripts/` | both | `memory-state.sh` and `memory-check.py` (write the git-derived state, refuse memory git contradicts; `odd_tasks.py` is the task-file parser it shares with the telemetry); `pre-pr-pass.sh` (stamp the commit that passed the gate; with `TDD="strict"` it refuses a code commit no test commit precedes; `TDD_EXEMPT="<reason>"` skips it once); `push-pr.sh` (push and open the PR, refusing an unstamped HEAD and a stale base, plus what the config sets: `TICKET_LINE`, `TITLE_PATTERN`, `TITLE_MAX`, `ATTRIBUTION`); `sync-skills.sh` (copy `.agents/skills/` into `.claude/skills/`); `telemetry.py` (the telemetry event contract and its local SQLite store, `.orchestrator/telemetry/telemetry.db`: runs, tasks, agent runs, usage with its source, criteria; standard library only, no network, no model calls; `sync-criteria` projects the task files' criteria and task statuses, also run at session start and end; `cost` prints the API-equivalent estimate via `api_cost.py`; `usage`, `metrics` and `report` print Markdown reports via `reports.py`, read-only; `benchmark` compares two sets of benchmark results via `benchmark_report.py`) and `claude_transcript.py` (a Claude Code subagent's tokens from its transcript, read strictly and versioned: `unavailable` on any shape it doesn't know) |
| `.orchestrator/hooks/` | both | `decision-index.sh` (one line per ADR/decision in force, from `ADR_DIR`/`DECISION_LOG`; silent while they're empty), `session-memory.sh` (prints the memory for Codex), and `update-check.sh` (says when an orchestrator release is out or the workspace is behind the installed skill; the lookup runs in the background once a day), and `telemetry.sh` (the telemetry hooks' entry: never fails the session, prints nothing, notes errors in `.orchestrator/telemetry/errors.log`) |
| `.agents/skills/` | both | `sync-memory`, `orchestrator-metrics` (which telemetry command answers which question; the user runs it with `!` so it costs no tokens), the default standards `software-principles` and `design-patterns`, and `pre-pr-review` (Codex's version of the workflow). The one copy to edit |
| `.gitattributes` | both | Keeps scripts LF, so Git for Windows doesn't break them with CRLF |
| `CLAUDE.md` | Claude | Imports `AGENTS.md` and the two memory files |
| `.claude/settings.json` | Claude | The SessionStart decision index and update notice, the telemetry hooks (session start and end, subagent start and stop, Agent results; synchronous with a 5 s timeout, except SessionStart), `autoCompactWindow: 150000`, idle compaction from 100k (`env.CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS`), `skillListingMaxDescChars: 300`, `enabledPlugins` |
| `.claude/agents/` | Claude | `explorer` (Haiku), `architect` (Opus), `<repo-slug>-dev` (Sonnet, compacts at 150k): the source the Codex agents are rendered from |
| `.claude/workflows/pre-pr-review.js` | Claude | Saved workflow: `architect` reviewers per group of checklist items, then a Sonnet `architect` that tries to refute each finding |
| `.claude/skills/` | Claude | Copies of `.agents/skills/` except `CODEX_ONLY_SKILLS` |
| `.codex/agents/*.toml` | Codex | The same agents, rendered by `scripts/agent-to-codex.py`: no model (the spawn request picks the tier's), except `explorer` on the trivial model |
| `.codex/config.toml` | Codex | `model_auto_compact_token_limit = 150000`, `[agents]` default model (normal tier) and medium effort |
| `.codex/hooks.json` | Codex | SessionStart: the memory, the decision index and the update notice |
| `.gitignore` | both | Ignores the app repos, so the root versions only the orchestration layer |

With `--git` it runs `git init` at the root when the root isn't a repo yet and has subrepos. It doesn't commit.

With `--no-git` it runs no `git init` and writes no root `.gitignore`. `AGENTS.md` says the layer is
unversioned, and `orchestrator.conf` gets `ROOT_GIT="no"`, so `sync-memory` skips its commit. In
single-repo mode the new files go to the repo's `.git/info/exclude`, which is local and never
committed. The app repos still need git: the memory scripts read their commits and PRs.

## 3. Tailor what the script couldn't know

Edit the generated files. Replace every `TODO(orchestrator-setup)` marker:

- **`AGENTS.md`**: the stack per repo in the repo table and the commands block. Also "How the repos
  connect": how they depend on each other, where the contract between them is written, and where cross-repo
  decisions live.
- **The user's choices** (step 1): in *Standards*, drop or rewrite the rows the user declined and add theirs
  (delete a declined default skill from `.agents/skills/`), and make the *Standards digest* in
  `.claude/agents/architect.md` and each `*-dev.md` say the same (delete it when no standard is left); in the checklist's part C, drop, rewrite or add
  items, keeping the numbers that stay; `TDD`, `TDD_TEST_COMMIT`, `TDD_CODE_COMMIT`, `TITLE_PATTERN`,
  `TITLE_MAX` and `ATTRIBUTION` in `orchestrator.conf`. With `ATTRIBUTION="refuse"`, also add
  `"attribution": {"commit": "", "pr": ""}` to `.claude/settings.json` and a *Workspace rules* line saying so.
  Any other lasting preference the user stated goes to *Workspace rules*.
- **`AGENTS.md` › Repo guides**: one section per repo that has no `AGENTS.md`/`CLAUDE.md` of its own.
  Fill in the stack, the layout, the conventions the code and its history actually follow (commit and PR
  title format included) and the check commands. Take all of them from the code, not from assumptions. Keep each section under ~15 lines. Don't create a guide
  or skills inside the repo: the root never edits inside a repo.
- **Tickets, only if the project uses them**: add a step 0 to the feature flow in `AGENTS.md`. It
  searches for or creates the ticket, puts its key in briefs and PR bodies, and moves the ticket when the
  PR opens. Set `TICKET_LINE` in `orchestrator.conf` (e.g. `'^Jira: PROJ-[0-9]+'`) so `push-pr.sh`
  enforces it. Without a ticket system, leave the flow as it is. The memory's Ticket column then takes `—`.
- **Pre-PR gate**: in `.orchestrator/pre-pr-checklist.md` item 2, the exact local checks per repo and
  what CI runs instead. Drop item 17 if no repo has a user interface; otherwise name the repos it covers in
  the item. If a repo has CI that runs the full suite, add a *Test suites*
  rule to `AGENTS.md` › *Workspace rules* (locally only the tests for what changed; `gh pr checks` decides).
- **Review declined** (step 1): in `AGENTS.md` step 4, replace the `pre-pr-review` clause with "for a
  large one, `architect` reviews it against part B", and delete `.claude/workflows/` and
  `.agents/skills/pre-pr-review/`.
- **Two GitHub accounts on the machine** (plain `git push` authenticates as the wrong one): write a
  wrapper `.orchestrator/scripts/gh-git.sh <repo> <git args>` that passes the org account's
  `gh auth token` as a one-shot credential helper, and set `GIT_WRAPPER` to it. Never change git or gh config.
- **Decision index**: if a repo records ADRs or a decision log, set `ADR_DIR` and `DECISION_LOG` in
  `orchestrator.conf` and run `bash .orchestrator/hooks/decision-index.sh` once: it must print one line
  per decision in force. If the format differs (status in another place), adapt the awk in the hook.
  With no decision records, delete the hook and its SessionStart entries in `.claude/settings.json` and
  `.codex/hooks.json`.
- **Agents** (`.claude/agents/<repo>-dev.md`): stack, the files to read before coding, and the exact check
  commands for that repo, including how to run a single test (test-first needs it). `architect.md`: where
  the repos record decisions (ADRs, decision log, open questions); if they keep none, "ask the user". Then
  regenerate the Codex agents from them:
  `for f in .claude/agents/*.md; do python3 <this skill's directory>/scripts/agent-to-codex.py "$f" ".codex/agents/$(basename "${f%.md}").toml" <trivial model>; done`.
- **Model tiers**: if the repos make ~30 lines a poor line for *trivial* (generated code, large fixtures),
  adjust the table in `AGENTS.md` › *Token budget*.
- If a repo already has its own agents or skills, keep them as they are. A repo with neither uses the
  root's, which is the default case. The root never edits inside a repo. To reuse a repo's agents, render
  the Codex ones from them with `agent-to-codex.py` and point `.claude/agents` at them; a symlink works on
  macOS and Linux, but on Windows copy them, and note it in `AGENTS.md` so they're re-copied when the repo
  changes them.
- If a repo already ships a skill for a standard (its own `software-principles`, say), keep the root copy
  anyway: the orchestrator and `architect` read the root's. In briefs, point to the repo's copy when one
  exists.
- After any edit under `.agents/skills/`, run `bash .orchestrator/scripts/sync-skills.sh`.
- **Single-repo mode** (the root is the repo): delete "How the repos connect" and the sentence about
  the root being its own git repo. The orchestration files are committed in the repo itself.

Then check `grep -rn "TODO(orchestrator-setup)" AGENTS.md .orchestrator .agents .claude .codex memory`.
It should return nothing.

## 4. Verify and hand over

1. `for f in .orchestrator/scripts/*.sh .orchestrator/hooks/*.sh; do bash -n "$f"; done && python3 -m py_compile .orchestrator/scripts/memory-check.py`
   and `bash .orchestrator/scripts/sync-skills.sh --check`. With Codex, check that `.codex/config.toml` and
   `.codex/agents/*.toml` parse (`python3 -c "import tomllib,sys; [tomllib.load(open(f,'rb')) for f in sys.argv[1:]]" .codex/*.toml .codex/agents/*.toml`,
   Python 3.11+). With Claude Code and `node` installed, check the workflow wrapped in an async function
   (it uses top-level `await` and `return`): `{ echo '(async () => {'; sed 's/^export //' .claude/workflows/pre-pr-review.js; echo '})'; } > <scratch>/wf.js && node --check <scratch>/wf.js`.
2. Run `bash .orchestrator/scripts/memory-state.sh`, then `python3 .orchestrator/scripts/memory-check.py`.
   Without `gh` or a remote they warn and skip the PR part. They must not fail.
3. Unless `--no-git` was used, ask the user before the first commit at the root:
   `git add AGENTS.md CLAUDE.md .orchestrator .agents .claude .codex memory odd .gitignore .gitattributes && git commit`,
   with a message in the convention the user chose (leave out what the chosen tools didn't create). Never add a remote or push unless the user asks.
4. Report: files created, files skipped (already present), the TODOs left for the user, and how to start (`USAGE.md` in this skill's directory is the person-facing version)
   in each tool. Claude Code: open it at the workspace root; `/sync-memory` once per session; `/usage` to
   see what each skill, agent and plugin costs. Codex: trust the project, open `/hooks` once to approve
   the two SessionStart hooks, then `$sync-memory` once per session and `/status` for usage. In both,
   before each push: the gate, `bash .orchestrator/scripts/pre-pr-pass.sh`, `bash .orchestrator/scripts/push-pr.sh`.

## Update an existing workspace

A workspace set up with v0.1.0 or later is brought up to this skill's templates by a script, not by hand
(an older one goes through `scripts/migrate.sh` first). Only on the user's explicit yes in this session.

1. `bash <this skill's directory>/scripts/update.sh --dry-run <workspace-root>` and show the plan.
2. `bash <this skill's directory>/scripts/update.sh <workspace-root>`. It creates what is missing, updates a
   script only if it is still the template of the workspace's `TEMPLATE_VERSION`, keeps a script the user
   changed and writes the new template next to it as `<file>.new`, adds the missing telemetry hooks to
   `.claude/settings.json`, the missing lines to `.gitignore` and the missing keys to `orchestrator.conf`, and
   sets `TEMPLATE_VERSION` last. It refuses, changing nothing, when the version can't be established, the layer
   has uncommitted changes or an earlier `.new` differs; a failure midway lists what was done and what is
   pending. It never deletes and never commits. Use a release of the skill: `--dev` (an unreleased skill) is for
   testing it, not for workspaces in regular use, since at the next release a file it wrote that changed again
   comes as a `.new`.
3. Do what it lists under *Needs your attention*: merge each `.new` into its file (keeping the user's change)
   and delete it; when the user would rather keep their file as it is, delete the `.new` files and run
   `update.sh --keep-mine` once instead (it records each declined template in `.orchestrator/update-keep`, so
   the file is offered again only when its template changes), and apply the printed *Workspaces* steps to the text the script never edits (`AGENTS.md`,
   `odd/README.md`, `memory/`). Then the checks of step 4 above, a commit if the root is versioned, and a new
   session so the hooks load.
