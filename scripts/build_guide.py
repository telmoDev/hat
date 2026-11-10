#!/usr/bin/env python3
"""Build the global install's guide from the per-workspace template (G4, docs/meta-harness/guide-split.md).
  python3 scripts/build_guide.py           write guide/AGENTS.md, guide/rules.md, guide/agents/ and guide/skills/
  python3 scripts/build_guide.py --check   exit 1 if either differs from what would be written
templates/AGENTS.md stays the one source of the flow while both installs exist (v0.9.x): the common sections are
copied with their paths rewritten for the global layout, the project's sections become the rules.md template.
In the result, <hat> is this clone, <root> the project root and <state> the project's ~/.hat/projects/<id>/.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "templates", "AGENTS.md")
OUT = os.path.join(HERE, "guide")

# The project's own sections: they go to rules.md, not to the common guide.
PROJECT = ("Layout", "Commands", "Repo guides", "How the repos connect", "Workspace rules")

HEAD = """# hat guide

Guidance for the orchestrator of every hat project. The session start names the project: its root (`<root>`),
its state folder (`<state>`, under `~/.hat/projects/`) and this clone (`<hat>`). Read the project's own rules,
`<state>/rules.md`, after this file: its repos and commands, how the repos connect, and the lasting rules agreed
with the user, which win over any default here. Claude Code and Codex follow the same flow; what differs is only
in *Tool mapping* at the end.

## Project

The session start lists the project's repos, their base branches and their own guides (from `<state>/config`).
**Read the guide of the repo you are about to change before changing it.** A repo with no `CLAUDE.md`/`AGENTS.md`
of its own has its conventions under *Repo guides* in `<state>/rules.md`. They live there, not inside the repo.

Run git commands for application code inside the repo concerned. Each repo has its own branches, commits and pull
requests, so a cross-repo feature means one PR per repo.
"""

# Whole paragraphs that only make sense in a workspace with its own layer, and their global wording.
PARAGRAPHS = [
    ("**The orchestration layer lives only at this root**",
     "**hat writes nothing inside a project.** Its guide, scripts, agents and skills live in `<hat>`; the "
     "project's memory, task files, config, rules and telemetry live in `<state>`. Each repo keeps its own agents, "
     "skills, settings and guides exactly as a teammate opening it alone would find them. Never edit anything "
     "inside a repo to suit orchestration. If something doesn't fit a repo's setup, adapt it in `<state>`."),
    ("The engineering standards this workspace follows.",
     "The engineering standards a project follows. They start as hat's defaults, which hold for any stack; the "
     "user keeps, rewrites, drops or adds to them per project (`STANDARDS` in `<state>/config`, a project's own "
     "standard named in `<state>/rules.md`). Each is a skill, and the brief of every task its row covers names "
     "it. A short digest of the defaults is written into `hat-architect` and `hat-dev`, so every agent applies "
     "them without opening a file; a project's different standard reaches the agent through the brief."),
    ("Agents are defined twice from one source",
     "hat's agents are global, defined once per tool (`~/.claude/agents/hat-*.md`, `~/.codex/agents/hat_*.toml`) "
     "from `<hat>/guide/agents/`. A brief states the paths: the project root is `<root>`, the repo and its guide, "
     "and commands run from inside the repo concerned."),
    ("The root's skills live in `.agents/skills/`",
     "hat's skills live in `<hat>` and are linked into each tool's global skills folder by the install. A "
     "subagent may not get them as invocable skills, so the brief gives the path and the agent reads `SKILL.md` "
     "directly: `<hat>/templates/skills/<name>/SKILL.md`, or the repo's copy when it has one. A subagent never "
     "commits, branches or pushes unless the brief says to."),
]

# Plain substitutions, in order.
SUBS = [
    ("{{DEV_ROWS}}\n", "| `hat-dev` | normal (the tier the task needs) | implementation in one repo: the brief names "
     "the repo, its guide, its commands and the standards that apply |\n\n"),
    ("{{ROOT}}", "<root>"),
    ("`{{CODEX_TRIVIAL}}`", "`CODEX_TRIVIAL` (config)"),
    ("`{{CODEX_NORMAL}}`", "`CODEX_NORMAL` (config)"),
    ("`{{CODEX_HARD}}`", "`CODEX_HARD` (config)"),
    ("(the *Base branch* column under Layout)", "(the base branches the session start lists)"),
    ("(its guide, or its section under *Repo guides*)", "(its guide, or its section under *Repo guides* in `<state>/rules.md`)"),
    ("A repo with none uses the root's skills.", "A repo with none uses hat's skills."),
    ("; the user opted into it for this step on {{DATE}})", ")"),
    ("`odd/tasks/<feature>.md` (shape and rules in `odd/README.md`)",
     "`<state>/tasks/<feature>.md` (shape and rules in `<hat>/templates/odd/README.md`)"),
    ("odd/tasks/<feature>.md", "<state>/tasks/<feature>.md"),
    ("`.orchestrator/orchestrator.conf`", "`<state>/config`"),
    ("`orchestrator.conf`", "`<state>/config`"),
    ("`.orchestrator/pre-pr-checklist.md`", "the checklist (`<state>/checklist.md`, or `<hat>/templates/orchestrator/pre-pr-checklist.md`)"),
    (".orchestrator/scripts/", "<hat>/templates/orchestrator/scripts/"),
    ("`memory/PROJECT_STATE.md`", "`<state>/memory/PROJECT_STATE.md`"),
    ("`memory/PROGRESS.md`", "`<state>/memory/PROGRESS.md`"),
    ("`memory/DECISIONS.md`", "`<state>/memory/DECISIONS.md`"),
    ("`memory/NEXT_STEPS.md`", "`<state>/memory/NEXT_STEPS.md`"),
    ("### Session memory (`memory/`)", "### Session memory (`<state>/memory/`)"),
    ("`memory/`", "`<state>/memory/`"),
    ("`explorer`", "`hat-explorer`"),
    ("`architect`", "`hat-architect`"),
    ("`*-dev` agents", "`hat-dev` agent"),
    ("`*-dev` agent", "`hat-dev` agent"),
    ("`*-dev`", "`hat-dev`"),
    ("this workspace", "this project"),
    ("Update the skill or this project only", "Update hat only"),
]

TOOL_MAPPING = """## Tool mapping

The flow above is the same in both tools. Only these mechanics differ.

**Platforms.** hat runs on macOS, Linux and Windows. Its scripts are bash and Python 3: call them as
`bash <script>` and `python3 <script>`, never by their executable bit. On Windows, bash is Git Bash (Git for
Windows; for Codex, its `bin` folder on `PATH`) and Python may be `py -3` or `python`. Write paths with `/`.

| What | Claude Code | Codex |
|---|---|---|
| Memory at start (project, memory, decisions) | `~/.claude/settings.json` › SessionStart (`hat resolve`, then the header) | `~/.codex/AGENTS.md` points here; the orchestrator runs `hat context` (no verified global hooks yet) |
| Session handoff | `~/.claude/settings.json` › SessionEnd writes it, SessionStart shows it | read at the next start, as above |
| Spawn an agent on a tier | Agent tool with `subagent_type`, `model` (tier) and `effort: "medium"` | ask to spawn the named agent and name the tier's model in the request |
| Agent names | `hat-explorer`, `hat-architect`, `hat-dev` | `hat_explorer`, `hat_architect`, `hat_dev` |
| Continue an agent | `SendMessage` to it | follow up on its thread (`/subagents` lists them) |
| Skills | `~/.claude/skills/` (linked to `<hat>`); invoke `/sync-memory` | `~/.agents/skills/` (linked to `<hat>`); invoke `$sync-memory` |
| Small-task diff review (step 4) | `/code-review medium` on the branch | the orchestrator reviews part B itself, or one `hat-architect` on the normal tier |
| Large-task review (step 4) | skill `pre-pr-review` | skill `$pre-pr-review` (same groups and verifier) |
| Compaction | `autoCompactWindow` in `~/.claude/settings.json`: the install proposes 150k and an idle compaction from 100k, never sets them without the user's yes | `~/.codex/config.toml`: `model_auto_compact_token_limit` |
| Attribution off (only with `ATTRIBUTION="refuse"`) | `push-pr.sh` refuses it; `attribution` in `~/.claude/settings.json` stays the user's | `push-pr.sh` refuses it |
| Agent run figures (tokens, duration) | recorded by the telemetry hooks in `<state>/telemetry.db`: `telemetry.py report`, never copied into the run log | not recorded yet (Codex payloads unverified): the run log notes what the subagent's thread shows, otherwise `not reported` |
| Measure | `/usage` (share by skill, subagent, plugin, MCP) | `/status` |
"""

# The global agents, from the per-workspace agent templates. The brief gives <hat>, <root> and <state> as paths.
AGENT_COMMON = [
    ("{{ROOT}}/odd/tasks/<feature>.md", "<state>/tasks/<feature>.md"),
    ("`{{ROOT}}/.agents/skills/<name>/SKILL.md`", "`<hat>/templates/skills/<name>/SKILL.md`"),
    ("(from `{{ROOT}}/AGENTS.md` › *Standards*;", "(hat's default standards;"),
    ("`{{ROOT}}/AGENTS.md` › *Standards*", "the brief (it names the standards that apply)"),
    ("`{{ROOT}}/AGENTS.md` › *Model tiers*", "hat's guide › *Model tiers*"),
    ("never write `{{ROOT}}/memory/` or `{{ROOT}}/odd/`", "never write hat's state (`<state>`)"),
    ("Never edit `{{ROOT}}/memory/` or `{{ROOT}}/odd/`", "Never edit hat's state (`<state>`)"),
    ("`architect`", "`hat-architect`"),
    ("`explorer`", "`hat-explorer`"),
]
AGENTS = {
    "explorer.md": ("hat-explorer.md", [
        ("name: explorer", "name: hat-explorer"),
        ("across the repos of the {{NAME}} workspace ({{REPOS}})", "across the repos of the project the brief names"),
        ("You are the explorer for the {{NAME}} workspace at `{{ROOT}}`. Its repos are: {{REPOS}}.",
         "You are hat's explorer. The brief names the project root and its repos."),
    ]),
    "architect.md": ("hat-architect.md", [
        ("name: architect", "name: hat-architect"),
        ("across the repos of the {{NAME}} workspace", "across the repos of the project the brief names"),
        ("for the {{NAME}} workspace at `{{ROOT}}` (repos: {{REPOS}})", "for the project the brief names (root and repos)"),
        ("otherwise its section under *Repo guides* in `{{ROOT}}/AGENTS.md`",
         "otherwise its section under *Repo guides* in the project's rules (`<state>/rules.md`)"),
        ("- Decisions live in: TODO(orchestrator-setup): ADR folder, decision log or docs, per repo.",
         "- Decisions live where the project's config says (`ADR_DIR`, `DECISION_LOG`) or its rules name; the brief gives the paths."),
    ]),
    "developer.md": ("hat-dev.md", [
        ("name: {{AGENT}}", "name: hat-dev"),
        ("in the `{{REPO}}` repo of the {{NAME}} workspace", "in the one repo the brief names"),
        ("You implement changes in the `{{REPO}}` repository at `{{ROOT}}/{{REPO}}`.",
         "You implement changes in the one repository the brief names, at the path it gives."),
        ("Stack: TODO(orchestrator-setup): language, framework, package manager.",
         "Stack, commands and conventions: as the brief gives them, from the project's rules (`<state>/rules.md`)."),
        ("Read the repo's guide: {{REPO_GUIDE}}.",
         "Read the repo's guide the brief names: its own `CLAUDE.md`/`AGENTS.md`, or its section in the project's rules."),
        ("run the checks: TODO(orchestrator-setup): the repo's test command and its other local checks.",
         "run the checks the brief names: the repo's test command and its other local checks."),
    ]),
}

# The global skills, from the per-workspace ones: the same text with hat's paths.
SKILL_SUBS = [
    ("`.claude/workflows/pre-pr-review.js`", "the saved workflow of a per-project install"),
    ("`{{ROOT}}/.orchestrator/pre-pr-checklist.md`", "`<state>/checklist.md` (or `<hat>/templates/orchestrator/pre-pr-checklist.md`)"),
    ("{{ROOT}}/.orchestrator/pre-pr-checklist.md", "<state>/checklist.md (or <hat>/templates/orchestrator/pre-pr-checklist.md)"),
    ("{{ROOT}}/.orchestrator/telemetry/telemetry.db", "<state>/telemetry.db"),
    (".orchestrator/scripts/", "<hat>/templates/orchestrator/scripts/"),
    ("`.orchestrator/orchestrator.conf`", "`<state>/config`"),
    (".orchestrator/rates.json", "<hat>/templates/orchestrator/rates.json"),
    ("{{ROOT}}/memory/", "<state>/memory/"),
    ("`memory/PROJECT_STATE.md`", "`<state>/memory/PROJECT_STATE.md`"),
    ("`odd/tasks/*.md`", "`<state>/tasks/*.md`"),
    ("All commands run from the workspace root, `{{ROOT}}`.", "All commands run from the project root, `<root>`."),
    ("Workspace root: {{ROOT}}.", "Project root: <root>."),
    ("{{ROOT}}", "<root>"),
    ("this workspace", "this project"),
    ("workspace standards", "project standards"),
    ("`Doc: odd/tasks/<feature>.md`", "`Doc: tasks/<feature>.md`"),
    ("(AGENTS.md flow step 4), for tools without the saved workflow (Codex)", "(hat's guide, flow step 4)"),
    (" Claude Code runs .claude/workflows/pre-pr-review.js instead.", ""),
    ("architect subagents", "hat-architect subagents"),
    ("one architect per finding", "one hat-architect per finding"),
]

RULES_HEAD = """# Project rules

This project's own guidance, read after hat's guide (`<hat>/guide/AGENTS.md`); it wins over any default there.
Written by `hat project add` from what it can detect, then by the orchestrator and the user. hat never writes
inside the project's repos.
"""


def sections(text):
    """[(title or None, text)] split at '## ' headings."""
    parts = re.split(r"(?m)^(?=## )", text)
    out = []
    for p in parts:
        m = re.match(r"## (.+)\n", p)
        out.append((m.group(1).strip() if m else None, p))
    return out


def build():
    with open(SRC, encoding="utf-8") as f:
        src = f.read()
    guide, rules = [HEAD], [RULES_HEAD]
    for title, body in sections(src):
        if title is None:
            continue
        if title in PROJECT:
            if title == "Layout":
                continue  # the repos table comes from config, shown at session start
            if title == "Workspace rules":
                body = body.replace("## Workspace rules", "## Rules")
                body = body.replace("working in this workspace", "working in this project")
                body = body.replace("`memory/DECISIONS.md`", "`<state>/memory/DECISIONS.md`")
                body = body.replace("over any default in this file", "over any default in hat's guide")
            rules.append("\n" + body.rstrip("\n") + "\n")
            continue
        if title == "Tool mapping":
            guide.append("\n" + TOOL_MAPPING)
            continue
        for start, new in PARAGRAPHS:
            body = re.sub(r"(?m)^" + re.escape(start) + r".*$", lambda m, n=new: n, body)
        for old, new in SUBS:
            body = body.replace(old, new)
        guide.append("\n" + body.rstrip("\n") + "\n")
    rules_text = "".join(rules).replace("TODO(orchestrator-setup)", "TODO(hat)")
    out = {"AGENTS.md": "".join(guide), "rules.md": rules_text}
    for src_name, (name, subs) in AGENTS.items():
        with open(os.path.join(HERE, "templates", "agents", src_name), encoding="utf-8") as f:
            text = f.read()
        for old, new in subs + AGENT_COMMON:
            text = text.replace(old, new)
        out["agents/" + name] = text
    skills = os.path.join(HERE, "templates", "skills")
    for name in sorted(os.listdir(skills)):
        with open(os.path.join(skills, name, "SKILL.md"), encoding="utf-8") as f:
            text = f.read()
        for old, new in SKILL_SUBS:
            text = text.replace(old, new)
        out["skills/%s/SKILL.md" % name] = text
    return out


def main(argv):
    want = build()
    if "--check" in argv:
        stale = []
        for name, text in want.items():
            try:
                with open(os.path.join(OUT, name), encoding="utf-8") as f:
                    if f.read() != text:
                        stale.append(name)
            except FileNotFoundError:
                stale.append(name)
        if stale:
            print("build_guide: guide/%s out of date: run python3 scripts/build_guide.py" % ", guide/".join(stale))
            return 1
        return 0
    for name, text in want.items():
        os.makedirs(os.path.dirname(os.path.join(OUT, name)), exist_ok=True)
        with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
