---
name: pre-pr-review
description: Part B of the pre-PR gate for a large task (hat's guide, flow step 4): hat-architect subagents review the branch against groups of checklist items, then one hat-architect per finding tries to refute it. Use once the owning agent reports part A green.
---

# Pre-PR review (part B, large tasks)

The same review as the saved workflow of a per-project install, run by hand with subagents. Keep the two in step:
the groups below match the workflow's `GROUPS`, and both follow the item numbers of
`<state>/checklist.md` (or `<hat>/templates/orchestrator/pre-pr-checklist.md`).

Inputs: `repo`, `branch`, `base` (default `main`), `ticket`, `spec`, `outcome` (the outcome block),
`tier` (`trivial`, `normal` or `hard`; default `normal`).

## 1. Context for every subagent

Paste this into each brief, filled in:

```
Project root: <root>. Repo: <root>/<repo>. Branch: <branch>, base origin/<base>. Ticket: <ticket>.
Spec the diff implements: <spec>  (none given: find the spec and the decisions the diff cites; AGENTS.md says where they live)
Outcome the diff must meet: <outcome>  (none given: report the checklist's *Outcome met* item as failed)
The checklist is <state>/checklist.md (or <hat>/templates/orchestrator/pre-pr-checklist.md). Start from
`git -C <root>/<repo> diff --stat origin/<base>...<branch>`, then open only the files that carry risk for your items.
Read-only: never edit, commit, branch or push. Review as the human reviewer would: report only defects that
break a checklist item, not style preferences.
```

## 2. Review: one `architect` per group, in parallel

Model: the normal tier unless `tier` is `hard`, then the hard tier (AGENTS.md › *Model tiers*); medium effort.

| Group | Checklist items |
|---|---|
| flow | in part B (contract line by line, repo rules and project standards, outcome met, test first when TDD is on) |
| quality | in part C, every one of them |

An item that names the repos it covers applies only to those. Ask each: "Check the checklist items <items> against this branch's diff. Return every failure as one line
`item · file:line · what is wrong and what the rule or spec says`, or `none`."

## 3. Verify: one `architect` on the normal tier per finding, in parallel

At most 8 per group; report the rest as unverified. Ask each: "A reviewer claims this branch fails checklist
item <item>: <file>:<line>: <summary>. Try to refute it: read the code and the spec or rule it cites. Answer
`refuted` if the claim is wrong, already handled, or not what the item asks, else `stands`, with one line why.
If uncertain, `stands`."

## 4. Result

Keep the findings that stand (and the unverified ones, marked). None: `PASS`. Otherwise `FAIL` with the
numbered list. Hand the result back to AGENTS.md flow step 4; this skill never stamps or pushes.
