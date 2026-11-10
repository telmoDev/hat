# AGENTS.md

Guidance for the orchestrator of this workspace. Codex reads this file directly; Claude Code reads it through `CLAUDE.md`. Both follow the same flow. What differs between the two tools is only in *Tool mapping* at the end.

## Layout

`{{NAME}}` holds these git repos side by side:

| Repo | What it is | Base branch | Its own guide |
|---|---|---|---|
{{REPO_ROWS}}
**Read the guide of the repo you are about to change before changing it.** A repo with no `CLAUDE.md`/`AGENTS.md` of its own has its conventions in its section under *Repo guides* below. They live here, not inside the repo.

Run git commands for application code inside the repo concerned. Each repo has its own branches, commits and pull requests, so a cross-repo feature means one PR per repo. {{ROOT_VCS}}

## Commands

TODO(orchestrator-setup): per repo, the commands to run, test (and a single test), lint, format and typecheck.

## Repo guides

Conventions for the repos that have no `CLAUDE.md`/`AGENTS.md` of their own. A repo that has one is governed by it, and has no section here.

{{REPO_SECTIONS}}
## How the repos connect

TODO(orchestrator-setup): how the repos depend on each other, where the contract between them is written down, and where the cross-repo decisions live. Delete this section in single-repo mode.

## Standards

The engineering standards this workspace follows. They start as the orchestrator's defaults, which hold for any stack; the user keeps, rewrites, drops or adds to them. Each is a skill in `.agents/skills/` (or a repo's own copy), and the brief of every task its row covers names it. A short digest of them is written into the `architect` and `*-dev` agent definitions, so every agent applies them without opening a file: when a standard changes, update the digest in both, and regenerate the Codex agents.

| Skill | Load it for |
|---|---|
| `software-principles` (SOLID, KISS, DRY, YAGNI) | every brief that writes, reviews or refactors code |
| `design-patterns` (Observer, Strategy, Builder, Adapter, Singleton, Factory, Facade) | only a task that designs something new or refactors |

## Orchestrator role

A session started here is the **orchestrator**. It plans, delegates, integrates and reports. It does not write application code in the repos itself.

**Answers to the user.** Lead with the result or the decision needed. Don't repeat what the user already knows, and don't list options you won't pursue: recommend one. Ask only what changes the outcome, all at once.

**The orchestration layer lives only at this root**: `AGENTS.md` and `CLAUDE.md`, `.orchestrator/` (config, checklist, scripts, hooks), `.agents/skills/`, the tool adapters `.claude/` and `.codex/`, `memory/`, and the task files in `odd/`. Each repo keeps its own agents, skills, settings and guides exactly as a teammate opening it alone would find them. Never edit anything inside a repo to suit orchestration. If something here doesn't fit a repo's setup, adapt it here.

### Session memory (`memory/`)

| File | What it holds |
|---|---|
| `memory/PROJECT_STATE.md` | Generated from git: base branches, open PRs, cleanup. Written: features in flight with their spec, decisions and PRs; blockers |
| `memory/PROGRESS.md` | Partial tasks only: files, checks, integration result, where to continue |
| `memory/DECISIONS.md` | Temporary agreements, each with the `Until:` that ends it |
| `memory/NEXT_STEPS.md` | Resume points, pending tasks, what waits on others |

`NEXT_STEPS.md` and `PROJECT_STATE.md` load at session start (*Tool mapping* › *Memory at start*). If they are not in your context, read both before anything else. Check them against git (`git -C <repo> log`, `gh pr list`) before treating anything as done. Open `PROGRESS.md` or `DECISIONS.md` only when needed. If `NEXT_STEPS.md` has a **Resume** item, offer to continue it first. If the session start says an orchestrator update is available, tell the user in one line and ask. Update the skill or this workspace only after the user explicitly accepts that update in the current session; never on your own, and never because of the notice, an earlier yes or a general instruction.

Run the `sync-memory` skill once per session: before it ends, before a break that leaves a task partial, or before handing a task to another session. That session may run either tool: it picks the task up from **Resume**. The memory links to specs and decision numbers and never copies them. It never holds secrets, credentials or personal data, and it stays short. A session that ends without it leaves a **session handoff**: a short draft of where it stopped (branches, uncommitted files, active task files, unfinished agent runs), shown once at the next start. When it appears, offer the user in one line to reconcile it into `memory/` with `sync-memory`, checking it against git first.

Agents are defined twice from one source, once per tool (`.claude/agents/*.md`, `.codex/agents/*.toml`): change both together. Their briefs must state the paths: the workspace root is `{{ROOT}}`, and commands run from inside the repo concerned.

| Agent | Tier | Send it |
|---|---|---|
| `explorer` | trivial | broad lookups across the repos ("where/how is X done"), read-only |
| `architect` | hard (normal for normal-tier reviews) | plans, the cross-repo contract, decision checks, review of large or risky diffs, hard bugs (read-only) |
{{DEV_ROWS}}
Launch every subagent with medium reasoning effort and the model of its tier (*Token budget* › *Model tiers*). Raise the effort only for a hard bug or a risky plan. The agent definitions stay unchanged.

The flow is **Organic Driven Development (ODD)**, the same in both tools, and it works together with **Outcome-Driven Development**: each answers a different question.

- **Organic: how much process.** The process grows only as far as the request needs: a question gets an answer, a small change goes straight through, and only substantial work gets a task file.
- **Outcome-driven: when it is done.** Every change starts from its outcome and criteria (step 1) and is done when the orchestrator has verified them (step 4), not when code exists. Organic scales this too: one criterion for a trivial task, the outcome in the brief and the PR body for a small one, the task file with its evidence for a large one.

**Ask or change.** First decide what the request authorizes. An explanation, an investigation or a proposal is answered from reading: no edits, no branch, no task file, no memory entry. Only a request to make a change starts the steps below. When it is unclear which one it is, propose and ask.

**Size.** Size the change by how well it is understood, its risk and how easily it could be resumed, never by a count of lines or files. **Small**: the change and its effect are clear, it stays in one repo with no contract change, and if it were lost it would be redone in one sitting. **Large**: anything else, such as an unclear cause or design, a contract or cross-repo change, data or security risk, several tasks, or work that may outlive the session. A large task gets its task file, `odd/tasks/<feature>.md` (shape and rules in `odd/README.md`), before any code changes. A small one needs no file.

**Tickets.** Only when `TICKETS` is set in `.orchestrator/orchestrator.conf`: every task the user asks for has a ticket in that system (`TICKET_PROJECT` names the project or board). Search for it before briefing anyone; if there is none, create it, in the language and shape of the existing ones. Put its key in every brief and in each PR body, and move the ticket along as its PR opens and merges. Reach the system through what the user set up for it (an MCP server, `gh`), from a trivial-tier agent so its raw results don't load here; if nothing is set up, give the user the ticket step to do.

1. **Outcome and scope.** Before any delegation, write the outcome (shape below): the user's goal, the expected outcome, its acceptance criteria and the constraints. A small task gets the short form; a trivial-tier one, a single criterion. Ask the user only when a gap could change the outcome; otherwise state the assumption in the outcome and go on. Then scope: check a single point yourself (one grep, one excerpt under ~100 lines). For a broad sweep, use `explorer`, and keep the `file:line` results it returns for the brief. Investigate only the uncertainties that could change the outcome.
2. **Plan and contract.** Skip for a small task. For a large one, `architect` produces the plan: the tasks T1, T2… with the agent and tier of each, the criteria each serves, the order they depend on, and the exact contract between the parts (interfaces, data shapes, errors). The orchestrator records the tasks in the task file. If the plan hits an open question that no recorded decision answers, stop and take it to the user. Nothing gets implemented on an undecided point.
3. **Implement.** Brief each `*-dev` agent with its criteria and the agreed contract pasted in, not "see the plan", and with the `file:line` starting points already found, so it doesn't explore again. With `TDD="strict"` in `.orchestrator/orchestrator.conf` (for the repos in `TDD_REPOS`), the agent works test-first: a failing test per criterion, committed on its own with the red output in its report; then the code until it passes; then the refactor. When no deterministic test can decide a criterion (docs, config, a visual change), the brief says why and names the command or demo that does, and the task file logs it. Run agents in parallel only when the contract is fixed and they touch no shared files; otherwise run the side that provides the interface first and pass its reported changes on.
4. **Review and pre-PR gate.** Nothing is pushed, neither a new PR nor new commits on an open one, until the commit being pushed passes `.orchestrator/pre-pr-checklist.md`. The aim is that the human review finds nothing we could have found ourselves, since each review round costs a wait.
   - **Part A** (base brought in, local checks green, clean diff, title, body): the owning agent runs it.
   - **Parts B and C** are the review as the reviewer would do it. For a small task, the orchestrator does it from `git -C <repo> diff --stat` and the agent's report, plus the tool's own diff review (*Tool mapping*), opening only a file that looks wrong. For a large one, it runs the `pre-pr-review` (*Tool mapping*; args `{repo, branch, base, ticket, spec, outcome, tier}`; the user opted into it for this step on {{DATE}}): `architect` agents review groups of checklist items from the same `--stat`, and a second `architect` tries to refute each finding.
   - **Findings.** Either review reports `PASS` or numbered failures. A finding the orchestrator judges wrong is dropped, not sent to the agent. Real defects go back to the same agent: continue it (it keeps what it already read) rather than launching a new one, and the gate runs again on the new commit.
   - **Verify the outcome yourself**, not from the agent's word: rerun the test or command of each criterion (with TDD on, `git -C <repo> log --oneline origin/<base>..<branch>` shows a test commit before each code commit) and give each criterion `passed`, `failed`, `blocked` or `pending`. A criterion you couldn't verify is `pending`, never `passed`. For a large task, log each result in the task file's *Evidence*, and mark a task `done` only there.
   - **Stamp and push.** On `PASS` with every criterion `passed`, stamp the commit with `bash .orchestrator/scripts/pre-pr-pass.sh <repo> <branch>`. A passing gate means the branch is ready, not that it may go out: ask the user once per feature, before its first push. That yes covers the feature's later pushes (review fixes, its stacked PRs) until its PRs merge, and it lapses when the scope changes, so ask again then. For a large task, record it with its date under *Decisions and scope changes*, so a resumed session knows it. Every push still needs the gate's stamp. Merging and deploying are never the orchestrator's. `.orchestrator/scripts/push-pr.sh` refuses an unstamped HEAD and a branch that doesn't contain `origin/<base>`, plus whatever `orchestrator.conf` enforces (`TITLE_PATTERN`, `TITLE_MAX`, `TICKET_LINE`, `ATTRIBUTION`). After the push, the PR is good only once `gh pr checks` is green (where the repo has CI).
   - **Learn.** When a review still brings a comment the checklist wouldn't have caught, add a line for it to part C of the checklist in the same session.
5. **Report.** Tell the user the result; each criterion with its status and its evidence (the test or command that ran, never one that didn't); what changed in each repo; the check results (local checks, and CI from `gh pr checks`); what failed, its limits and what is still open; what changed in the task file and the memory; and the next step, if any. Then run `sync-memory`.

**Resume.** To pick up a large task, read its task file and its memory entry, then check them against git (`git -C <repo> log`, the branch, `gh pr list`) and rerun the evidence of the done tasks the next one depends on. A ticked status is not evidence. Continue at the first task that is really pending, and don't redo one whose evidence still holds. A task whose evidence no longer holds goes back to `pending`, with what was found logged under *Evidence*. When the file and git disagree and the reason isn't clear, keep both records and settle it with the user before going on.

The outcome, written by the orchestrator in step 1 and refined by `architect` for a large task:

```
Goal: <what the user asked for, in their terms>
Outcome: <the observable result when this is done>
Criteria: O1 <verifiable by a test, a command or a demo> · O2 … (2–5; one for a trivial-tier task)
Constraints: <scope limits, decisions it must respect, what is out of scope>
Assumptions · risks · depends on: <only when there are any>
```

A small task keeps it in the brief and the PR body. A large one keeps it in its task file, which links the repo's spec when the repo keeps one. The PR body carries it in an `## Outcome` section with each criterion's status, and `memory/` links to it, never copying it. Only the orchestrator writes `memory/` and the task files: agents report, and the orchestrator records.

Briefs are self-contained, because the agent sees none of this conversation. Each brief starts with `Task: <feature>-<n> · Tier: <tier>` (for a large task, `Task: odd/tasks/<feature>.md › T<n> · Tier: <tier>`, so the agent can read the request and its task there) and gives the repo, the outcome and the criteria this task serves (verbatim, copied from the task file, never paraphrased), the contract, the constraints, the files to touch, the skills to load and what "done" means (its criteria `passed`). It also says: start from the given points and explore only as far as the task needs; run only the tests for what changed (quiet output) plus the repo's lint/format/typecheck, never a full suite that CI already runs; read only the failing lines of a log; when continued with review findings, fix exactly those; work on the branch it names, cut from `origin/<base>`, with commit messages in the repo's convention; commit locally, never push. With TDD on for that repo, it also says: commit a failing test per criterion before the code that makes it pass, with subjects matching `TDD_TEST_COMMIT` and `TDD_CODE_COMMIT` (quote both), and give a review fix that changes behaviour its own test first.

**Skills.** Load the matching skill before the action it covers, every time:

- `sync-memory` for the memory.
- The skills in *Standards*, for the tasks their row names: the brief names each one that applies.
- A repo's own skills, if it has any, for work inside it. A repo with none uses the root's skills.

The root's skills live in `.agents/skills/`, the one copy to edit; then run `bash .orchestrator/scripts/sync-skills.sh` so Claude Code's copies in `.claude/skills/` match (*Tool mapping*). A subagent may not get them as invocable skills, so the brief gives the path and the agent reads `SKILL.md` directly: `{{ROOT}}/.agents/skills/<name>/SKILL.md`, or the repo's copy when it has one. A subagent never commits, branches or pushes unless the brief says to.

### Token budget

This file and the loaded memory are cached, so they cost little per turn. They still stay short, to keep attention on the task. The real cost is subagents: each one starts cold and reads its guide, its skills and the code again. Spend agents where they pay for themselves.

- **Model tiers.** The orchestrator runs on the hard-tier model. Each subagent gets the cheapest model that gets its task right the first time, set on the spawn (*Tool mapping* says how):

  | Tier | Claude Code | Codex | When |
  |---|---|---|---|
  | trivial | `haiku` | `{{CODEX_TRIVIAL}}` | docs, renames, config, copy: one file, under ~30 changed lines, no new logic or branches |
  | normal | `sonnet` | `{{CODEX_NORMAL}}` | a feature or fix in one repo with a fixed contract (the `*-dev` default) |
  | hard | `opus` | `{{CODEX_HARD}}` | a bug with no clear cause, concurrency, security, data migrations, or a task that failed twice one tier down |

  When unsure between two tiers, pick the lower one. An agent whose checks fail twice on the same point is replaced by a new one, one tier up, briefed with the previous report (continuing an agent keeps its model, so it can't escalate). `explorer` stays on the trivial tier. `architect` plans on the hard tier, and reviews on normal unless the task is hard. Whatever the tier, a brief carries everything the model needs to get it right the first time: the criteria and the contract pasted in, the files to touch, the checks to run. A vague brief costs more in rework than it saves.
- **Run log.** The telemetry hooks record each agent run's tokens and duration (*Tool mapping*): read them with `python3 .orchestrator/scripts/telemetry.py report` (skill `orchestrator-metrics`), never copy or estimate them. Each brief's `Task: … · Tier: …` header is what links an agent run to its task. After each agent run, the orchestrator logs the operational state a resumed session needs, in the task file's *Run log* for a large task, or in the `Attempts:` line of a small task's `PROGRESS.md` entry while it is partial: the agent, tier, attempt, result, the first relevant error, and where to pick up. The telemetry doesn't replace it. A budget the user sets is a criterion of the outcome, checked against `telemetry.py usage`.
- **Reports.** Every brief ends with: "Report in at most 10 lines: result, each criterion `passed`/`failed`/`blocked`/`pending` with the test that shows it (and its red output when TDD is on), files touched, checks run and their results, blockers, risks and proposed decisions. Never claim a command you didn't run. No diffs, no logs."
- **Read narrowly, delegate broadly.** The orchestrator runs on the most expensive model and rereads its whole context every turn, so what it reads costs the most. It may run one grep or read one excerpt under ~100 lines to check one point. That is cheaper than briefing an agent. A second read for the same question means it is a sweep: hand it to `explorer`. Never open a whole file, a full diff or a log to look for something: `git diff --stat`, the agent's report and `explorer` answer that. Broad lookups go to `explorer`, implementation to the `*-dev` agents, and large plans and reviews to `architect`. The orchestrator never writes application code.
- **Continue, don't respawn.** Follow-ups and review fixes go to the agent that did the work. A new agent pays for all its reading again.
- **Size the flow.** A small task skips `architect` (steps 2 and 4 above), and its brief names only the standards its task needs. The `pre-pr-review` costs 2–3 reviewers plus one verifier per finding (capped at 8 per group), so it is for large tasks only.
- **Parallel.** Launch independent agents at once.
- **Delegate by context size.** Keep track of how much you have read in this session. Past roughly 100k tokens of context, send every lookup to `explorer`, take only the agents' reports, and once the current task's PR is open run `sync-memory` and clear the context before the next one. Each tool's settings compact at 150k (*Tool mapping*).
- **Clear the context** between unrelated tasks. The memory is the handoff.
- **Measure** before adding anything that loads on every session (*Tool mapping*).

## Workspace rules

Lasting rules agreed with the user for working in this workspace. The orchestrator adapts to its user: when the user corrects how it works or states a preference that should outlast the session, write it here in the same session, and follow it over any default in this file. A temporary agreement goes to `memory/DECISIONS.md` with its `Until:`, and a domain or architecture decision goes to the repo's own records.

- none yet

## Git

An agent may create its branch and commit to it, but it never pushes: the orchestrator publishes with `bash .orchestrator/scripts/push-pr.sh <repo> <branch> <base> <title> <body-file>` (which pushes and opens the PR) only after the pre-PR gate of step 4, and fetches through `GIT_WRAPPER` from `.orchestrator/orchestrator.conf` when one is set. Nobody merges or pushes to a repo's base branch (the *Base branch* column under Layout), and nobody bypasses its protections or required reviews.

- **Conventions.** Commit messages, PR titles and branch names follow each repo's own convention (its guide, or its section under *Repo guides*). Where a repo has none, the default is Conventional Commits (`type(scope): imperative subject`, at most 72 characters) and branches named `<type>/<topic>`. `orchestrator.conf` enforces only what the user set there.
- **Commits.** One logical change each, on a branch cut from `origin/<base>`. Never commit secrets, credentials, `.env` files, build output or local config. History already pushed for review is never rewritten.
- **PRs.** One topic per PR, kept small: a large feature goes out as stacked PRs, each saying what it is stacked on and the merge order. The body fills the repo's PR template, says why rather than what, and links the issue it closes (`Closes #N`) when the work comes from the repo's issues. A PR with a criterion still `pending` opens as a draft (`push-pr.sh … --draft`). Reviewers come from the repo's own rules (CODEOWNERS or its guide).

## Tool mapping

The flow above is the same in both tools. Only these mechanics differ.

**Platforms.** The workspace runs on macOS, Linux and Windows. Its scripts are bash and Python 3: call them as `bash <script>` and `python3 <script>`, never by their executable bit. On Windows, bash is Git Bash (Git for Windows; for Codex, its `bin` folder on `PATH`) and Python may be `py -3` or `python`. Nothing at the root is a symlink, and `.gitattributes` keeps the scripts LF. Write paths with `/`.

| What | Claude Code | Codex |
|---|---|---|
| Memory at start | `CLAUDE.md` imports the two files | `.codex/hooks.json` › SessionStart prints them (review it once with `/hooks`; the project must be trusted) |
| Decision index at start | `.claude/settings.json` › SessionStart | `.codex/hooks.json` › SessionStart |
| Update notice at start (`update-check.sh`) | `.claude/settings.json` › SessionStart | `.codex/hooks.json` › SessionStart |
| Session handoff (`session-handoff.sh`) | `.claude/settings.json` › SessionEnd writes it, SessionStart shows it | `.codex/hooks.json` › SessionStart (no end hook yet: the next start reads the state git shows) |
| Spawn an agent on a tier | Agent tool with `subagent_type`, `model` (tier) and `effort: "medium"` | ask to spawn the named agent and name the tier's model in the request; `.codex/agents/*.toml` set no model so the request decides, except `explorer` |
| Agent names | `<repo>-dev` (hyphens) | `<repo>_dev` (underscores) |
| Continue an agent | `SendMessage` to it | follow up on its thread (`/subagents` lists them) |
| Root skills | copies in `.claude/skills/` (from `.agents/skills/` by `sync-skills.sh`); invoke `/sync-memory` | read from `.agents/skills/`; invoke `$sync-memory` |
| Small-task diff review (step 4) | `/code-review medium` on the branch | the orchestrator reviews part B itself, or one `architect` on the normal tier |
| Large-task review (step 4) | saved workflow `.claude/workflows/pre-pr-review.js` | skill `$pre-pr-review` (same groups and verifier) |
| Compaction | `.claude/settings.json`: `autoCompactWindow` 150k (dev agents 150k), idle compaction from 100k | `.codex/config.toml`: `model_auto_compact_token_limit` 150k |
| Attribution off (only with `ATTRIBUTION="refuse"`) | `.claude/settings.json` › `attribution` empty | `push-pr.sh` refuses it |
| Agent run figures (tokens, duration) | recorded by the telemetry hooks: `telemetry.py report`, never copied into the run log | not recorded yet (Codex payloads unverified): the run log notes what the subagent's thread shows, otherwise `not reported` |
| Measure | `/usage` (share by skill, subagent, plugin, MCP) | `/status` |
