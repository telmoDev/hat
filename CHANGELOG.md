# Changelog

Versions follow [Semantic Versioning](https://semver.org/): a **patch** fixes, a **minor** adds without
breaking existing workspaces, a **major** needs a workspace migration. Before 1.0.0 a minor may still need
one; its *Workspaces* line says so. Each workspace records the version it was set up with in
`.orchestrator/orchestrator.conf` › `TEMPLATE_VERSION`.

Every entry has two parts: what changed, and **Workspaces**: what an agent must do to bring an existing
workspace up to this version ("nothing" when templates didn't change). `release.sh` turns *Unreleased*
into the new version's section.

## Unreleased

- The test suite is hermetic: every test module imports `tests/hermetic.py` first (a test checks it), so no test
  reads or writes the real hat home, even where this clone is a registered hat project; `smoke.sh` does the same.
  `tests/__init__.py` lets one module run as `tests.test_<name>`. The unreleased-skill update test uses an
  untagged clone, so it no longer fails on the commit of a release.

- `hat migrate --refresh`, for a workspace still in use between its migration and its cleanup: brings its new
  memory, task files, telemetry, handoff and layer copy into hat's state, keeps the reviewed `rules.md` and
  `config`, appends any project paragraph new since the migration to `rules.md`, and reports conf keys that now
  differ. A `GIT_WRAPPER` inside the old layer moves to `<state>/bin/` at the migration, and the config points at
  it; the scripts take an absolute `GIT_WRAPPER` as it is.

## v0.9.1 — 2026-11-10

- One hat for several Claude Code accounts: the global install honours `CLAUDE_CONFIG_DIR`
  (`CLAUDE_CONFIG_DIR=~/.claude-work bash install.sh --global` wires the account that alias uses). Every account's
  hooks call the same clone and share `~/.hat`, so projects, memory and telemetry are the same whichever account
  runs the session. What was installed is recorded per config folder (a v0.9.0 record reads as `~/.claude`'s);
  uninstalling one account leaves the others whole, including the Codex links they share; `hat doctor` checks
  every account hat is installed in.

- Per-project git settings as configuration (roadmap X4), from migrating a real workspace that had forked its
  scripts for them: `PR_TARGETS` (per repo, the branch PRs open into when it isn't the base they branch from;
  `push-pr.sh` opens the PR there and never pushes it, `memory-state.sh` never lists it for cleanup) and
  `GH_USER` (the gh account the project's repos need; `push-pr.sh` and `memory-state.sh` run gh with its token).
  The secret check no longer takes a long lowercase branch slug with digits for a token. `hat status` says when a
  migrated workspace is waiting for its cleanup.
  **Workspaces:** `bash <skill>/scripts/update.sh <workspace-root>` adds the two keys; a workspace that forked
  `push-pr.sh` or `memory-state.sh` for them can set the keys and take the template's scripts back.

## v0.9.0 — 2026-11-10

- README and INSTALL describe hat as it is now: installed once for every project (`bash install.sh --global`),
  projects registered with `hat.py project add`, their state in `~/.hat/projects/<id>/`, the commands
  (`status`, `doctor`, `migrate`, `commit`), and the per-project layer still supported through v0.9.x. An agent
  installing hat tells the person what the global install changes and installs it on their yes.

- Compaction that loses nothing (global install G8; compaction stays on): a `PreCompact` hook saves where the
  session is (dirty branches, every active task file with its `Next:`, unfinished agent runs) whether or not the
  memory was synced, and the `SessionStart` that follows (`source: compact`, same session) shows it once, next to
  the header and memory those hooks already reload. Telemetry records each compaction as `session.compacted`
  with its trigger and the context size before it; `telemetry.py report` shows them per run. Payloads checked on a
  live session first. Wired in the global install and in the per-project settings template.
  **Workspaces:** `bash <skill>/scripts/update.sh <workspace-root>` adds the two `PreCompact` hooks.

- Global install G6b: `hat migrate <workspace> --cleanup`, after a verified migration and only when the layer is
  unchanged since, removes hat's old layer in one commit at the workspace root (git can undo it): `AGENTS.md`,
  `CLAUDE.md`, `.orchestrator/`, `memory/`, `odd/`, hat's skills, agents and workflow, and hat's hooks inside
  `.claude/settings.json` and `.codex/hooks.json`. The user's own skills and settings and the app repos are never
  touched; the project then runs on hat. At session start, where hat isn't running yet, one line offers the next
  step: migrate a workspace with the old layer, clean up a migrated one, or register an unregistered git repo
  (decision G-D1).

- Global install G6a: `hat migrate <workspace> [--dry-run]` moves a workspace with the per-project layer to the
  global install, saving what is the project's first. Each layer file is compared with the templates of its
  `TEMPLATE_VERSION`, of every later release and of the current clone (placeholders filled at setup count as
  wildcards; generated copies and caches are skipped): the project sections of `AGENTS.md` and every paragraph
  that differs go verbatim to `rules.md`, other changed or added files to `overrides/`, its own checklist to
  `checklist.md`. Memory, task files, conf, telemetry (SQLite backup) and handoff state are copied as they are, and
  the whole layer to `migrated-layer/` (git-ignored). Nothing is registered until a check confirms every
  project-specific paragraph is in `rules.md`. The workspace is never changed: it keeps its own layer, which the
  global hooks leave alone, until it is cleaned up (G6b).

- Global install G5 (roadmap X4, configure instead of forking): no layer file cites a checklist item by number
  any more (`pre-pr-pass.sh`, `pre-pr-review`): a project with its own checklist keeps the template's files. The
  ticket system is configuration: `TICKETS` (e.g. `jira`, `github`) and `TICKET_PROJECT` in the config, and an
  `AGENTS.md` › **Tickets** paragraph (search or create the task's ticket before briefing, its key in every brief
  and PR body, moved along with its PR; through an MCP server or `gh`, from a trivial-tier agent); `sync-memory`
  checks ticket keys against it. Without `TICKETS`, nothing changes.
  **Workspaces:** run `bash <skill>/scripts/update.sh <workspace-root>` (it adds `TICKETS` and `TICKET_PROJECT` to
  the conf). By hand, only if the workspace uses tickets: add the template's **Tickets** paragraph to `AGENTS.md`
  before step 1 of the flow, set the two keys, and drop the ticket steps the workspace had written itself.

- Global install G7: `hat status` shows every registered project apart: whether it runs on hat or still has its
  own layer (or its root is gone), its resume point, its active task files with their `Next:`, and its last
  session from its telemetry. `hat doctor` checks this machine: Python, `claude`, the global install (what is
  missing), hat's home as a git repo (and uncommitted changes), each project's root; exit 1 on a problem. Both
  read only.

- From the first live run of the global install: `hat project remove <id>` (unregisters; the project's state stays
  in the home, never deleted); hat's home keeps `backup/` (settings may hold tokens) and `install.json` out of
  git, and an older home gets the missing ignore lines; a commit no longer fails on a path that was never
  committed. Only `sync-memory` and `orchestrator-metrics` are linked globally, because every session on the
  machine lists the descriptions of global skills; the standards and `pre-pr-review` are read by path from
  `<hat>/guide/skills/`, and a reinstall unlinks what an older install linked. A test runs a whole session
  through the global hooks and checks nothing is written inside the project.

- Global install G3: `bash install.sh --global` wires hat once, for every project: the hooks in
  `~/.claude/settings.json` (through `scripts/hat-hook.sh`, acting only in registered projects), a pointer of
  under 90 words in `~/.claude/CLAUDE.md` (and `~/.codex/AGENTS.md` when Codex is set up), the agents `hat-explorer`,
  `hat-architect`, `hat-dev` in `~/.claude/agents/`, and the skills linked from `~/.claude/skills/` and
  `~/.agents/skills/` to `guide/skills/` (global versions built from `templates/skills/`). Every other setting is
  kept; `settings.json` is backed up in `~/.hat/backup/` first; a file that exists and isn't hat's stops it before
  any change; compaction is only proposed. `--uninstall` removes exactly what it added (recorded in
  `~/.hat/install.json`), `--check` reports what is missing.

- Global install G2b: `scripts/hat-hook.sh <hook>`, the one entry the global hooks will call. It finds the project
  from the event's `cwd`; outside a registered project, or in one that still has its own layer, it does nothing;
  otherwise it runs the hook with the project's state. `hat context` prints the session-start header (project,
  root, state, where the guide and the project's rules are, its repos). hat's home is a local git repo: each
  registration is a commit, `hat commit <message>` records the current project's memory and tasks (telemetry,
  handoff and tmp stay out), and `sync-memory` uses it under the global install. A script the orchestrator runs by
  hand from the clone finds its project from the folder it runs in. Nothing is wired yet (G3).

- Global install G2a: every script finds the project's files through `layout.py` / `layout.sh`. In a workspace
  nothing changes. With `HAT_STATE` (the project's `~/.hat/projects/<id>/`) and `HAT_ROOT` set, as the global
  hooks will set them, the config, memory, task files (`tasks/`), telemetry store, session handoff and pre-PR
  stamps are read and written there, the scripts run straight from the clone, and nothing is written inside the
  project. Nothing sets `HAT_STATE` yet.

- `guide/` (global install G4): the guide every hat project will share, `guide/AGENTS.md`, the template of a
  project's own rules, `guide/rules.md` (commands, repo guides, how the repos connect, rules), and the three global
  agents `guide/agents/hat-explorer.md`, `hat-architect.md` and `hat-dev.md` (one dev agent for every repo, which
  takes its repo, guide, commands and standards from the brief). All are built from `templates/` by
  `scripts/build_guide.py`, so the flow keeps one source while both installs exist; a test fails when they drift.
  No rule changes. Nothing uses them yet.

- `scripts/hat.py` (global install G1): hat's home `~/.hat/` (`HAT_HOME` overrides it) with its project registry
  `projects.toml`. `hat project add [<root>]` registers a project (default: the git top level, or the folder for a
  multi-repo workspace) and creates `projects/<id>/` for its state; `project list` and `project move <id> <root>`;
  `hat resolve [<folder>]` prints the project a folder belongs to, or nothing, for the hooks to call in every
  session. One root per project (nested roots refused); nothing is ever written inside a project. Nothing uses it
  yet.

## v0.8.0 — 2026-11-10

- **Known limits of this release.** Live on a real workspace: the update kept every user file, telemetry recorded
  main-session and agent usage with full coverage (hooks p95 33 ms, no errors), and a synced session left no
  handoff draft. Not yet seen live: the draft after a session that ends *without* `sync-memory` (covered by
  `tests/test_session_handoff.py`), and a `PostToolUseFailure` payload (no tool failed). Codex records nothing yet
  (F1-11 partial): its adapter waits for verified payloads.

- `update.sh --keep-mine`: a file the user changed is kept as it is, without a `.new`, and its declined template
  recorded in `.orchestrator/update-keep`; the next updates offer it again only when its template changes.
  Before, every update wrote the same `.new` next to each file the user had chosen to keep.

- `AGENTS.md` › *Orchestrator role*: **Answers to the user**: lead with the result or the decision needed, don't
  repeat what the user knows, recommend one option instead of listing those not pursued, ask only what changes
  the outcome, all at once. Agents' reports were already capped; the orchestrator's own answers weren't.

- `scripts/update.py` no longer recreates a root skill the workspace had and removed (a standard it keeps in a
  repo's own copy, or dropped); skills new since the workspace's version are still created. `sync-skills.sh`
  leaves the update's `.new` copies out of `.claude/skills/`.

- `harness.py doctor` and [docs/harnesses.md](docs/harnesses.md): the harness capability contract (meta-harness X2).
  Each runtime declares what it can really do for hat (`health_check`, `collect_events`, `usage`, `execute`,
  `status`, `cancel`) as `verified`, `unverified` or `unsupported`; Claude Code has events, usage and its health
  check verified, Codex nothing yet. `doctor` says whether each runtime is installed and wired in the workspace
  (naming any missing hook). No network, no model calls, never starts a session; nothing in the flow uses it yet.

- `knowledge.py validate|index` (meta-harness K1): OKF v0.2 knowledge bundles. `validate` checks OKF conformance
  (permissive: unknown types, keys and broken links are never errors) plus provenance (`sources`), trust
  (`generated`, `verified`, actors, ISO timestamps with an offset), lifecycle (`status`, `stale_after`), the
  `x_scope` extension, log dates and secrets; v0.1 concepts pass with legacy warnings. `index` writes each
  directory's `index.md` listing (by type, then subdirectories) inside a generated block, keeping hand-written text
  and never touching concepts. Standard library only (PyYAML when installed). Checked on the four official OKF
  sample bundles: 0 errors, both YAML readers agree on all 54 frontmatters. Nothing in the flow uses it yet.

- Phase 1 review ([docs/meta-harness/phase-1-review.md](docs/meta-harness/phase-1-review.md)): hook latency, concurrency,
  privacy and the update path measured on copies of real workspaces. Two fixes: `errors.log` names an unknown
  payload key only when it looks like an identifier (free text in a key is never logged), and the session handoff
  lists only the task files the session changed, counting the other active ones in one line.
  `docs/telemetry.md` › *Scope*: every metric belongs to its project's store; no global store.

- The repository is now `telmoDev/hat`: the README says what hat does today, where it is going (the meta-harness
  roadmap) and how to install it; `INSTALL.md` clones from the new URL. The skill (`orchestrator-setup`), the
  clone folder and the workspace paths keep their names.

- **Session handoff**: memory between sessions no longer depends on the model running `sync-memory`. A session
  that ends without updating `memory/` leaves a short draft of where it stopped, shown once at the next start
  with an offer to reconcile it into `memory/`: per repo the branch, uncommitted files (paths, at most three) and
  commits not in `origin/<base>`; each active task file with its `Next:` and open tasks; agent runs that never
  finished (from the telemetry store). A session killed without its end hook is caught by the next start; so is
  every Codex session, which has no end hook yet. Nothing shows after a synced session or when there is nothing
  to hand off. Local git only, no network or model calls, never file contents, diffs or commit messages; a line
  that looks like a secret is left out (`memory-check.py`'s rule). State in `.orchestrator/tmp/handoff/`;
  `SESSION_HANDOFF="off"` turns it off. `scripts/update.py` adds its Claude Code hooks.

- `AGENTS.md`: Organic Driven Development and Outcome-Driven Development spelled out as complementary, one
  answering how much process a request needs, the other when it is done (its criteria verified). Same rules as
  before, clearer wording.

- `docs/telemetry.md`: the telemetry contract in one place (events and their keys, statuses, figures and their
  sources, the Claude Code adapter, recovery, the store, settings) and the F1 criteria with the tests that prove
  each. `tests/test_telemetry_doc.py` fails when the document and the code disagree. Templates unchanged.

- Benchmark fixture: its HTTP server no longer looks the host name up on every start (`http.server` does, and on
  the macOS CI runner each lookup took ~35 s, measured: the job went from ~40 s to ~11 min). This changes every
  task's hash: earlier results (the B1 pilots) stay as they are and don't compare with new runs.
- `tests/smoke.sh` lists the 20 slowest tests (`unittest --durations`, Python 3.12+).

- `telemetry.py benchmark`: with fewer than 3 runs on a side, no reading at all (no "fewer/more tokens in every
  run", no quality verdict): only n, medians and ranges, quality, coverage and the warning. Seen in pilot 2, where
  one run a side read as a result. Pilot 2's results (B1, Haiku, once per flow; main session measured) are
  versioned in `benchmark/results/pilot2-b1-*/`; earlier ones are unchanged.

- Telemetry measures the main (orchestrator) session too, not only the agent runs: `claude:<session>:main`, read
  from the session's own transcript with the same strict parser (`unavailable` on any shape it doesn't know; never
  prompts, answers or code). Queued at SessionStart and read only at SessionEnd, never while the session grows;
  unreadable there, it stays pending and the next session's start makes the last attempt (also for a session
  killed without SessionEnd). Idempotent; a resumed session replaces its totals. The main transcript holds no
  subagent lines (checked on 97 real ones), so nothing is counted twice. Never a delegation (no agent id).
  `TELEMETRY_TRANSCRIPTS="off"` records it unavailable. Event contract unchanged.
  - Reports: a `main` row in `usage`, a *Main session* table in `metrics`, and the run report's line "Main session
    tokens · agent runs tokens". Delegations, coverage and efficiency are the agent runs' as before.
  - Benchmark results: `main_tokens`, `tokens` (agent runs; zero when none ran) and `total_tokens`; the comparison
    uses the total and adds *Tokens by kind* (main, agents, input, output, cache read and write, agent coverage).

- Benchmark B1: its check expected five functions, but `Cart.total` also calls `Cart.quantity` and `catalog.get`
  (seen in the pilot, where both flows rightly named them and were graded wrong). Now the seven. A result records
  the task hash it is graded under, and `regraded_from` with the earlier one when the grading changed after
  `prepare`. Pilot results: the originals stay as they were (3/4, old hash); `*-regraded` re-check the stored
  answers with no model (4/4, new hash, `regraded_from` the old).

- Benchmark (`benchmark/`, `scripts/benchmark.py`): five fixed tasks on a fixed two-repo fixture (B1 explore,
  B2 endpoint, B3 bug across modules, B4 frontend, B5 refactor), checked without any model: B1's answer by its
  JSON facts against the code, B2–B4 by hidden acceptance tests, B5 by an output probe before and after plus the
  repo's tests. `prepare` builds a workspace for a task and a flow (`current` or `v0.7.0`) with the same
  measurement layer in both; `run` is the only model step, on demand, and needs `--model` (`ORCH_BENCH_NO_MODEL`
  makes it refuse: the tests set it); `result` writes a JSON with ids, versions,
  criteria, test counts and telemetry (never prompts, answers, code, paths or transcripts; files consulted
  `unavailable`). Reference solutions prove every task solvable and every check discriminating.
- `telemetry.py benchmark <dirA> <dirB>` (`benchmark_report.py`): compares results only for the same task hash
  (request and criteria, checks, fixture, grading code, session settings), runtime and named models; a run with no
  named model or a blocked criterion isn't compared. Quality and consumption apart, n, median and range; a quality
  regression (any mandatory criterion passing less often) is never an efficiency gain; overlapping ranges show no difference; wall time apart from cumulative agent time.

- Telemetry reports (`reports.py`, read-only, no model calls): `telemetry.py usage | metrics | report`, Markdown,
  by agent, model, runtime, project, task or run, with filters (`--project --runtime --model --agent --task
  --status --since --until`). Skill `orchestrator-metrics` says which command answers which question; run with
  `!`, a report costs no tokens.
  - Delegations exclude failed launches. Succeeded is n/m over finished delegations (finished without a runtime
    error, not that the work is right); 0/0 is "no data". Running agent runs are in progress or unfinished and
    count as neither. Retries follow a failed run of the same task and agent; re-invocations are any repeat.
  - Coverage: finished delegations with reported usage. A finished one without usage counts in coverage, adds no
    tokens; `—` is not available, never zero. Tokens add up only for verified runtimes (Claude Code).
  - Run wall time apart from cumulative agent time (parallel agents add up, so it isn't wall time).
  - A session that launched no agent is still a run: counted (with its wall time) by runtime, project and run;
    reported apart by agent, model and task ("Runs: N, of which M had no agent runs"); left out, and said so,
    by an agent, model, task or status filter.
  - Efficiency and API-equivalent cost per task only when every task of the row is fully covered; else
    "incomplete", never an average of the covered part.
  - Quality keeps tasks with and without criteria apart; criteria are not attributed to runs.
  - The instrumentation's own overhead, from `ingest_log`.
- `AGENTS.md` › *Run log*: tokens and duration come from `telemetry.py report`; the run log (and a small task's
  `PROGRESS.md` line, now `Attempts:` instead of `Cost:`) keeps agent, tier, attempt, result, first relevant
  error and where to pick up. With Codex, not recorded yet, it still notes the thread's tokens.


- Local operational telemetry, part 3 (ODD criteria): `telemetry.py sync-criteria`, also run by the SessionStart
  and SessionEnd hooks, projects each task file's *Evidence* results (criterion, result, date; never the command
  or its output) and its *Tasks* statuses into the store, as `criterion.verified` and `task.*` events. The
  Markdown stays the source of truth: nothing is written back, and the projection can be rebuilt.
  - Criteria link to agent runs through the task (`<feature>#T<n>`), the id the brief's header gives.
  - A criterion's `run_id` stays NULL: an *Evidence* line names the date, task, criterion and result, not the
    session that ran the check, and when a line appeared is no evidence of who wrote it. Attribution to a run
    needs explicit evidence that the run made the check, which the task file doesn't carry today.
  - A replayed or moved line is the same event; a later result on the same day wins.
  - A small task has no task file: its criteria (in its PR body) are not recorded.
  - `odd_tasks.py`: the task-file parser, moved out of `memory-check.py` unchanged and shared with the telemetry.


- API-equivalent cost (`telemetry.py cost`, `api_cost.py`): what the recorded usage would cost through the
  provider's API, at the rates in `.orchestrator/rates.json`. Always labelled an estimate, with the rates' version,
  date and source, and a warning that it is not what a subscription (Claude Pro or Max, ChatGPT Plus) costs.
  - `rates.json` ships empty: no price is assumed. Entries are checked; a bad one is left out and named.
  - The rate in force on the invocation's day applies. Only `runtime_reported` usage is priced: never estimated
    or inferred figures, nor `calculated` ones (allowed only as a deterministic calculation from runtime_reported
    figures, which no record can show today). Anything else, a missing rate or an unverified runtime is shown as
    not priced, with the reason. `Decimal`.
  - Rule: Claude Code (Anthropic: input excludes cache). Codex has none until its real figures are checked.
  - Cache writes: Anthropic prices 5-minute and 1-hour writes differently, and the transcripts give them as one
    figure. The sum is valued at the single, combined `cache_write` rate of `rates.json` (the 5-minute rate
    undervalues 1-hour writes, the 1-hour rate overvalues 5-minute ones), so the report is titled "estimated,
    combined cache-write rate" and is never an exact API cost.


- Local operational telemetry, part 1 (the core; no hook calls it yet):
  - `.orchestrator/scripts/telemetry.py`: a versioned event contract (`schema_version` 1: run, task, agent,
    usage, criterion and blocked events), checked on the way in. Each payload key must be in the contract and
    its strings are short, so prompts, responses and file content can't get in. Usage carries its source
    (`runtime_reported`, `calculated`, `estimated` or `unavailable`), and `unavailable` carries no tokens.
  - A SQLite store, `.orchestrator/telemetry/telemetry.db`, with versioned migrations, WAL and a busy timeout.
    Event ids are deterministic, so a replayed event counts once. A resumed or compacted session reopens its
    run instead of starting another. Standard library only, no network, no model calls.
  - `.orchestrator/hooks/telemetry.sh`, the entry the hooks will call: it never fails the session and never
    prints, noting errors in `.orchestrator/telemetry/errors.log`. Each call logs its own duration in
    `ingest_log`, so the instrumentation's overhead is measured too. `TELEMETRY="off"` turns it off.
  - `tests/test_telemetry.py` (run by `tests/smoke.sh`).

- Local operational telemetry, part 2 (Claude Code): the hooks in `.claude/settings.json` record each session
  (a run), each subagent (start, stop, model, the task from its brief's `Task:` header, attempts at the same
  task) and its tokens, without model calls.
  - The hooks are synchronous with a 5 s timeout, except SessionStart: `claude -p` kills async hooks still
    running at teardown, which would lose the last SubagentStop. A call takes ~30 ms (one bash and one Python
    start, a SQLite write; SubagentStop also reads the transcript: 64 ms on a 14.6 MB one), printing
    nothing; 5 s covers a locked database (2 s busy timeout) without holding a session's exit for long.
  - Claude Code's own agents (prompt suggestions, `/btw`) are not recorded: SubagentStop fires for them with an
    empty `agent_type`, which an Agent-tool subagent never has (checked on 489 real subagents). Limitation: in a
    session started with `--agent`, they carry that agent's name and can't be told apart.
  - A failed Agent call (it never started a subagent; cancelling a running one doesn't fire the hook) is its own
    invocation, `claude:tool:<tool_use_id>`, with only `error: interrupt|error` and the reported duration, never
    the error text; it never counts as an attempt at its task.
  - Briefs name their task on the first line (`Task: odd/tasks/<feature>.md › T<n> …` or `Task: <feature>-<n> ·`);
    words after `T<n>` (`T2 review`) are allowed. Only that line is read; the prompt is never stored.
  - The transcript is read after the stop, not at it: checked live, at SubagentStop it may still lack the
    subagent's last request (written ~0.1 s later), which recorded 1 of 2 requests as if complete. A stopped
    agent's transcript is read by a later hook of the session once the stop is 2 s old, at SessionEnd, or at the
    next SessionStart for a session that ended without one (migration 2: `claude_pending`); only then may it be
    `unavailable`. Real figures replace an earlier `unavailable`, never the reverse.
  - Tokens come from the subagent's transcript once it has stopped (`claude_transcript.py`): no documented hook gives
    them, since the Agent result's usage covers only its last request and a background agent's result none. The
    format is private, so the reader is strict and versioned (`claude-transcript/2`): anything it doesn't
    recognize records `unavailable`, never a partial sum. Each request spans several lines with the same figures
    but an output that grows while it streams; it counts once, with its final output. Lines of one request that
    differ in anything else give `unavailable`.
    `TELEMETRY_TRANSCRIPTS="off"` records `unavailable` instead.
  - A subagent that stops is `completed`, not `success`: the criteria say whether its work holds.
  - `AGENTS.md` › *Tool mapping*: the run log no longer copies the Agent result's tokens (last request only).
  - Codex: not wired. Its adapter waits for real hook payloads.

- `scripts/update.sh`: updates a workspace set up with v0.1.0 or later to the installed skill's templates. It
  creates what's missing and updates a script only if it is still the template of the workspace's
  `TEMPLATE_VERSION` (read from that release's tag); a script you changed is kept, with the new template as
  `<file>.new` to merge by hand (an earlier, different `.new` stops it). `.claude/settings.json` gains only the
  missing telemetry hooks, `.gitignore` the missing lines, `orchestrator.conf` the missing keys, and
  `TEMPLATE_VERSION` last. Text you adapt (`AGENTS.md`, `odd/README.md`, `memory/`, task files) is never edited:
  it prints the Workspaces steps to apply. Everything is checked and planned before the first write; a failure
  midway lists what was done and what is pending, with the version unchanged. Refuses a missing or untagged
  `TEMPLATE_VERSION`, uncommitted changes in the layer, a pre-0.1.0 workspace and a skill that is not a release
  (`--dev` updates without claiming a version, for testing the skill only: at the next release, a file it wrote
  that changed again comes as `.new`). `--dry-run` shows the plan. Never deletes, never commits.
- The telemetry store refuses a schema newer than its script knows: it is left as is, never migrated down, and
  the error says to update the orchestrator.
- `INSTALL.md` and `USAGE.md`: the telemetry's install, settings, privacy, recovery and compatibility.

**Workspaces:** run `bash <skill>/scripts/update.sh <workspace-root>` (`--dry-run` first to see the plan) and
  merge any `.new` it lists. Then by hand: in `AGENTS.md`, replace the *Run log* bullet and the *Tool mapping*
  row on run-log figures with the template's; in `odd/README.md`, the "Figures are…" rule and the *Run log* line;
  in `memory/PROGRESS.md`, the `Cost:` line with `Attempts:`; in *Orchestrator role*, the paragraph that opens
  the flow ("The flow is **Organic Driven Development (ODD)**…") with the template's; in *Session memory*, the
  sentence on the session handoff after "…and it stays short.", and the *Tool mapping* row "Session handoff";
  in *Orchestrator role*, add the template's **Answers to the user** paragraph after the first one.
  With Codex, add the template's `session-handoff.sh start` entry to `.codex/hooks.json` › SessionStart.
  Restart the sessions so the hooks load.

## v0.7.0 — 2026-10-27

- The flow is **Organic Driven Development (ODD)**: the process grows only as far as the request needs.
  "Outcome-driven" stays as the criteria layer inside it, without the acronym.
  - *Ask or change*: an explanation, investigation or proposal edits nothing and creates no task file or memory entry.
  - Small/large is sized by understanding, risk and how easily the work resumes, not by "~100 changed lines".
  - A large task gets `odd/tasks/<feature>.md` before any code changes (shape and rules in the new
    `odd/README.md`): the request quoted exactly, outcome, specs, tasks T1… with dependencies and status,
    evidence, run log, decisions and scope changes. Briefs name `odd/tasks/<feature>.md › T<n>` and copy its
    criteria word for word; the agents read it and never write it.
  - *Resume*: from the task file checked against git, at the first task really pending; a status without
    evidence that holds goes back to `pending`.
  - A passing gate no longer pushes on its own: the orchestrator asks the user once per feature before its first
    push. The yes covers its later pushes and PRs until they merge, lapses on a change of scope, and a large
    task records it in its task file.
  - The report adds failures and limits, task-file and memory changes, and the next step.
  - When no deterministic test fits a criterion, the brief says why and names the check that decides it.
- *Cost per task* becomes *Run log*: agent, tier, attempt, tokens and duration as the tool reported them (or
  `not reported`), first error and result, in the task file. Still no estimates and no budget enforcement; a
  budget the user sets is a criterion of the outcome.
- `memory-check.py` scans `odd/tasks/*.md` for secrets and refuses: a `PROGRESS.md` `Doc:` line naming a missing
  or finished task file; a task `done` with no *Evidence* line; `Status: done` with tasks not done; an *In flight*
  `N/M passed` cell that the task file's evidence contradicts.
- Codex reads `AGENTS.md` only up to `project_doc_max_bytes` (32 KiB by default) and silently drops the rest,
  *Tool mapping* first. `.codex/config.toml` sets it to 64 KiB, and `memory-check.py` fails when `AGENTS.md`
  outgrows it (a warning past 85%). `sync-memory` keeps the task files current and commits `odd/` with `memory/`.
- `tests/smoke.sh` checks that the ODD rules reach both tools and that `memory-check.py` covers the task files.

**Workspaces:** optional, recommended. Copy `templates/odd/README.md` to `odd/README.md`. In `AGENTS.md`, replace the
flow's opening paragraph through step 3, the *Stamp and push* bullet, step 5 with the new *Resume* paragraph,
the outcome paragraph and the briefs' first sentence, *Cost per task* (now *Run log*), and add the *Run log
figures* row to *Tool mapping*; add `odd/` to the layer list under *Orchestrator role*. Take the new lines in
`.claude/agents/{architect,*-dev}.md` and regenerate the Codex agents. Replace `memory/PROGRESS.md`'s entry
shape, `.agents/skills/sync-memory/SKILL.md` (then `sync-skills.sh`) and `.orchestrator/scripts/memory-check.py`.
With Codex, add `project_doc_max_bytes = 65536` to `.codex/config.toml`. In single-repo mode without git, add
`/odd/` to `.git/info/exclude`.

## v0.6.0 — 2026-10-24

- Setup asks in one message: what it found and a table of every choice with its default filled in from the
  repos, instead of a dozen questions one by one. Versioning still has no default and is always asked.
- `AGENTS.md` flow step 4 (review and pre-PR gate), one ~350-word paragraph, is split into short bullets: part A,
  parts B and C, findings, verifying the outcome, stamp and push, learning from reviews. Same rules.
- Checklist item 9 says what `pre-pr-pass.sh` can't see: it reads commit subjects and order, not whether a test
  really failed, so the red output and the test are the evidence.

**Workspaces:** optional. Replace step 4 of the flow in `AGENTS.md` with the template's (keep the workspace's own
date of the `pre-pr-review` opt-in), and add the three lines after item 9's text in
`.orchestrator/pre-pr-checklist.md`. Setup changes need nothing.

## v0.5.1 — 2026-10-24

- The `pre-pr-review` defaults to the normal tier, as `AGENTS.md` › *Model tiers* says: without `tier`, its
  reviewers ran on Opus. Pass `tier: "hard"` for a hard task.
- `ATTRIBUTION="refuse"` refuses only AI attribution: a `Co-authored-by` naming a person no longer blocks the push.
- A smoke test (`tests/smoke.sh`), run by CI on macOS, Linux and Windows: it scaffolds a two-repo workspace,
  runs the checks of `SKILL.md` step 4 and exercises `pre-pr-pass.sh` and `push-pr.sh`.

**Workspaces:** optional. Copy `templates/orchestrator/scripts/push-pr.sh` over `.orchestrator/scripts/push-pr.sh`;
in `.claude/workflows/pre-pr-review.js` set `reviewModel` as in the template; in
`.agents/skills/pre-pr-review/SKILL.md` make the `tier` default `normal`.

## v0.5.0 — 2026-10-23

- Standards that agents actually apply: transcripts showed dev agents told to "read software-principles"
  never opened it. The `architect` and `*-dev` definitions now carry a short *Standards digest*; the full
  skills are opened for plans and design reviews, and agents report which skills they read.
- A leaner orchestrator, which ran on the priciest model and processed half of all tokens: one read per
  question (a second one goes to `explorer`), never a whole file, diff or log; past ~100k tokens of context it
  delegates every lookup and clears after the task's PR. Compaction at 150k (was 200k) in both tools, idle
  compaction from 100k (was 120k).

**Workspaces:** optional. Add the *Standards digest* block to `.claude/agents/architect.md` and each
`*-dev.md` (as in `templates/agents/`) and regenerate `.codex/agents/` with `agent-to-codex.py`; copy the
*Read narrowly* and *Delegate by context size* bullets and the *Compaction* row into `AGENTS.md`; set
`autoCompactWindow` to 150000 and `CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS` to "100000" in
`.claude/settings.json`, and `model_auto_compact_token_limit = 150000` in `.codex/config.toml`.

## v0.4.0 — 2026-10-23

- Update notice: a SessionStart hook, `.orchestrator/hooks/update-check.sh`, says when a newer orchestrator
  release is out (looked up in the background, at most once a day, so the session never waits on the
  network) and when the workspace's `TEMPLATE_VERSION` is behind the installed skill. The session tells the
  user and asks; it updates only after the user explicitly accepts, and so does `INSTALL.md`, which now
  waits for a yes before moving the clone to a new release (and a separate yes per workspace). `UPDATE_CHECK="off"` silences it; setup asks (`scaffold.sh --no-update-check`).

**Workspaces:** optional. Copy `templates/orchestrator/hooks/update-check.sh` to `.orchestrator/hooks/`, add
`UPDATE_CHECK="on"` to `orchestrator.conf`, add the hook to SessionStart in `.claude/settings.json` and
`.codex/hooks.json` (as in the templates), and the *Update notice* row and the line after *Resume* to
`AGENTS.md`. Then set `TEMPLATE_VERSION` to this version.

## v0.3.0 — 2026-10-23

- Whether to version a workspace's orchestration layer is the user's call: setup always asks, with no
  default, and `scaffold.sh` refuses to run without `--git` or `--no-git`.

**Workspaces:** nothing.

## v0.2.0 — 2026-10-23

- `scripts/migrate.sh <workspace>` does the mechanical part of the v0.1.0 migration (moves, path
  rewrites, thin `CLAUDE.md`, new files, `.codex/`) and lists what an agent still edits by hand.
- `memory-check.py` no longer reads code blocks or inline code as PR references: the example
  `api #12 open, web #7 draft` in `PROJECT_STATE.md` failed the check in any repo with a remote.
  The In flight table now checks itself that each PR it lists exists, backticks or not.

- Examples no longer name real projects: `My.API` → `my-api-dev` for agent names, `'^Jira: PROJ-[0-9]+'`
  for `TICKET_LINE`.
- Good-practice defaults, adapted to the user. The orchestrator keeps its own way of working (outcome-driven
  flow, test-first, `software-principles`, `design-patterns`, the quality checklist), which holds for any
  stack; setup reads each repo's conventions from its history and asks which defaults to keep, rewrite or
  drop. New `AGENTS.md` › *Standards* lists the skills briefs name; *Workspace rules* records the user's
  corrections and preferences as they come.
- What belongs to the user's team is no longer imposed: commit and PR title format, attribution and the way
  the base is brought in follow each repo's convention. `push-pr.sh` enforces only what `orchestrator.conf`
  sets (`TITLE_PATTERN`, `TITLE_MAX`, `ATTRIBUTION="refuse"`, `TICKET_LINE`); the template's
  `.claude/settings.json` no longer empties attribution.
- `pre-pr-pass.sh` tells test commits from code commits with `TDD_TEST_COMMIT` and `TDD_CODE_COMMIT`
  (defaults: Conventional Commits) instead of hard-coded `test`/`feat`/`fix`.
- The checklist has three parts: A mechanical (1–5), B the flow's review (6–9), C quality (10–17, the
  defaults the user adapts, where lines from reviews also go). The review workflow and skill group by part,
  so `UI_REPOS` is gone: the UI item names the repos it covers.
- Git and PR defaults, for repos with no convention of their own: Conventional Commits and `<type>/<topic>`
  branches; one logical change per commit, no secrets, `.env`, build output or local config, no rewriting
  history pushed for review; one small topic per PR (stacked when large), the repo's PR template, why rather
  than what, `Closes #N`, a draft while a criterion is `pending`, reviewers from the repo's own rules. New
  checklist item 3 (clean diff).
- The guide, agents and checklist speak of contracts, interfaces and data shapes, not endpoints and payloads.

**Workspaces:** copy `templates/orchestrator/scripts/memory-check.py` over `.orchestrator/scripts/memory-check.py`.
The rest is optional; a workspace keeps working with its current files. To adopt it, copy `pre-pr-pass.sh`
and `push-pr.sh` together with these lines in `orchestrator.conf`: `TDD_TEST_COMMIT='^test(\(|:|!)'`,
`TDD_CODE_COMMIT='^(feat|fix)(\(|:|!)'`, and, to keep the old checks, `TITLE_MAX=72` and `ATTRIBUTION="refuse"`.
Copy the checklist, `.claude/workflows/pre-pr-review.js` and `.agents/skills/pre-pr-review/` together (they
share the numbering), moving the workspace's own review lines into part C. Add the *Standards* section to
`AGENTS.md` listing the standard skills the workspace already has.

## v0.1.0 — 2026-10-23

First release. The skill, until now kept in `~/.claude/skills/orchestrator-setup`, is shared by Claude
Code and Codex and runs on macOS, Linux and Windows.

- One guide, `AGENTS.md`, read by Codex directly and by Claude Code through `CLAUDE.md`. Shared files in
  `.orchestrator/` (config, checklist, scripts, hooks), `.agents/skills/` and `memory/`; `.claude/` and
  `.codex/` are thin adapters, and `AGENTS.md` › *Tool mapping* lists what differs.
- Outcome-driven flow (goal, outcome, criteria O1… verified by the orchestrator as
  `passed`/`failed`/`blocked`/`pending`), test-first enforced by `pre-pr-pass.sh` (`TDD`, `TDD_REPOS`,
  `TDD_SINCE`, `TDD_EXEMPT`), and model tiers (trivial/normal/hard) per tool.
- Codex: custom agents rendered from the Claude ones (`scripts/agent-to-codex.py`), `$pre-pr-review`
  skill mirroring the Claude workflow, SessionStart hooks for the memory and the decision index,
  `.codex/config.toml` with compaction and subagent defaults.
- Cross-platform: no symlinks in a workspace (`sync-skills.sh` copies skills), scripts called as
  `bash`/`python3`, `.gitattributes` keeps them LF, native `C:/` paths under Git Bash.
- `TDD_SINCE` with a bare date now means its midnight (git read it as that day at the current time, so
  the check skipped every commit made earlier that day); `HH:MM` accepted.
- `pre-pr-review` reviewers use the normal-tier model for any tier but hard.
- Briefs spell out the test-first commits; `WORD_BUDGET` 900 → 1200 to fit outcome and cost lines.
- Install by an agent from the repo link (`INSTALL.md`), `install.sh` with `--check` and
  `--uninstall` (symlink on macOS/Linux, junction on Windows), and `USAGE.md` for the person.

**Workspaces:** a workspace set up before this release has everything under `.claude/` (no
`TEMPLATE_VERSION`). To migrate: run `bash scripts/migrate.sh <workspace>` (from v0.1.1 on), or by hand: move `.claude/orchestrator.conf`, `pre-pr-checklist.md`, `scripts/` and
`hooks/` to `.orchestrator/`; move the root skills to `.agents/skills/` and run `sync-skills.sh`; turn
`CLAUDE.md` into `AGENTS.md` plus the thin `CLAUDE.md` (keep the workspace's own sections); update the
paths in settings, workflow, checklist and skills; add `.gitattributes`, `TEMPLATE_VERSION="0.1.0"`, and
`.codex/` if the workspace will use Codex. Check with step 4 of `SKILL.md`.
