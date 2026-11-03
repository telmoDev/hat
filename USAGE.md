# Working with the orchestrator

For the person who works with it. Your agent can summarize this for you in your language.

## The idea

You open your agent (Claude Code or Codex) at the root of a folder that holds your repos. That session is
the **orchestrator**: it plans, briefs helper agents, checks their work and reports to you. It does not
write application code itself. Helper agents do: `explorer` looks things up, `architect` plans and
reviews, one `<repo>-dev` per repo implements.

The way of working is **Organic Driven Development (ODD)**: the process grows only as far as your request
needs.

- **A question changes nothing.** Asking it to explain, investigate or propose gets you an answer, with no
  edits, branches or files. Only a request to change something starts the flow below.
- **Small or large, by understanding and risk**, not by size. A clear, low-risk change in one repo goes
  straight through. Anything unclear, risky, spread over several tasks or likely to outlive the session is
  large: it first gets a task file, `odd/tasks/<feature>.md`, with your request quoted exactly, the
  criteria, the tasks and their status, the evidence of each, and a run log (tokens and duration as the tool
  reported them, never estimated).
- **Resuming** a large task starts from that file, checked against git: it continues at the first task
  that is really pending, and doesn't trust a status that the evidence no longer backs.

Each change follows the same steps:

1. **Outcome first.** Before anything is built, the orchestrator writes down your goal, the observable
   result and 2–5 acceptance criteria (O1, O2…). It asks you only when a gap could change the result.
2. **Plan** (large tasks only): `architect` turns the criteria into steps and the exact contract between repos.
3. **Test first** (on by default). The dev agent writes a failing test per criterion, commits it, then the
   code that makes it pass. The gate refuses a code commit with no test commit before it.
4. **Pre-PR gate.** Nothing is pushed until the branch passes the checklist in
   `.orchestrator/pre-pr-checklist.md` and the orchestrator has rerun each criterion's test itself. Then it
   asks you once per feature before the first push; that yes covers its later pushes and PRs until they
   merge or the scope changes. It never merges or deploys.
5. **Report.** You get each criterion as `passed`, `failed`, `blocked` or `pending`, with the command that
   shows it, what failed or is still open, what changed in memory, and the next step. Nothing unverified is
   called done.

To save tokens, each helper runs on the cheapest model that can do the job right: **trivial** (small
docs/config), **normal** (a feature with a fixed contract), **hard** (unclear bugs, security, migrations).
An agent that fails twice is replaced one tier up.

## Setting up a workspace

Open your agent at the workspace root and say "implementa la estructura de orquestador" (or "set up the
orchestrator"). It reads your repos (stack, commands, how you write commits and PR titles), asks which tools
you use, your ticket system and whether to version the orchestration files in git, then shows you its defaults (design principles and patterns, test-first,
the quality checklist) so you keep, change or drop each one. Then it writes the files and lists what's left
for you to fill in.

## It adapts to you

The defaults are a starting point that works for any stack. Your conventions win: the orchestrator follows
each repo's guide and history, and when you correct how it works or state a preference, it writes it to
*Workspace rules* in `AGENTS.md` and follows it from then on. Your own standards are skills: add one to
`.agents/skills/` and a row to *Standards*.

## Every session

| | Claude Code | Codex |
|---|---|---|
| Start | open it at the workspace root; the memory loads by itself | open it at the root; the first time, trust the project and approve the two hooks in `/hooks` |
| Ask for work | describe the task; the orchestrator does the rest | same |
| Save the session's state | `/sync-memory` before you stop or take a break | `$sync-memory` |
| See what it costs | `/usage` | `/status` |
| Between unrelated tasks | `/clear` | start a new session |

`memory/` is the handoff: a session in either tool picks up where the last one stopped (*Resume* in
`memory/NEXT_STEPS.md`). You can switch tools between sessions.

## Good to know

- Your repos are never edited to suit the orchestrator; everything lives at the workspace root.
- Agents commit only on their own branch and never push. The orchestrator pushes with
  `bash .orchestrator/scripts/push-pr.sh` after the gate, and never merges.
- When a reviewer comments something the checklist would have caught, the orchestrator adds a line to the
  checklist so it doesn't happen again.
- When a new release is out, the session tells you at start (once the background check has seen it), and
  also when your workspace is behind the installed version. Nothing is updated unless you say yes. Turn it off with `UPDATE_CHECK="off"` in
  `.orchestrator/orchestrator.conf`.
- Update the skill: ask your agent to update the orchestrator. It tells you what changed and waits for your
  yes before moving to the latest release. Existing workspaces keep their files and their `TEMPLATE_VERSION`; ask the agent to
  bring a workspace up to date when you want it. It runs `scripts/update.sh`, which keeps every script you
  changed (the new version lands next to it as `<file>.new`), never touches your memory, task files or guide
  text, and lists what needs you: the `.new` files and the *Workspaces* notes of `CHANGELOG.md`.

## Local telemetry

The hooks record how each session went into a local SQLite file, so you can see what a run, task, agent or model
consumed and how it ended, without asking a model. No network, no extra model calls; a hook call takes a few
milliseconds and never stops your session (errors go to `.orchestrator/telemetry/errors.log`).

- **Where**: `.orchestrator/telemetry/telemetry.db`, ignored by git. Only you have it.
- **What it stores**: sessions (start, end, status), agent runs (agent type, model, the task named by the brief's
  `Task:` line, start, end, status, duration), their tokens as Claude Code reported them (each with its source:
  reported, or unavailable with the reason), the ODD criteria and task statuses read from `odd/tasks/` (criterion,
  result, date), and the hooks' own timing.
- **What it never stores**: prompts, briefs, agent replies, code, file contents, commands or their output, error
  texts.
- **Reports**: `python3 .orchestrator/scripts/telemetry.py report` (the last session), `usage`, `metrics` and
  `cost`, with `--by` and filters; the `orchestrator-metrics` skill lists them. Run them with `!` so they cost no
  tokens. `cost` is an API-equivalent estimate at the rates you put in `.orchestrator/rates.json` (empty at
  first), never what a subscription costs.
- **Settings** (`.orchestrator/orchestrator.conf`): `TELEMETRY="off"` records nothing; `TELEMETRY_TRANSCRIPTS="off"`
  stops reading Claude Code's subagent transcripts, so their tokens show as unavailable.
- **Codex** isn't recorded yet: its adapter waits for verified hook payloads.
- **Recovery**: deleting `.orchestrator/telemetry/` removes only the telemetry; your memory, task files and guide
  are elsewhere and untouched, and the next session starts a new store. `telemetry.py sync-criteria` rebuilds the
  criteria from the task files, but the usage, durations and costs of past sessions are gone for good. A damaged
  store shows in `errors.log`; move the file aside to start fresh.
- **Compatibility**: a store written by a newer orchestrator is never changed or migrated down by an older one:
  it refuses and says to update the orchestrator.
