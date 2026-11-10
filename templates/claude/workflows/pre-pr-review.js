export const meta = {
  name: 'pre-pr-review',
  description: 'Part B of the pre-PR gate: review a branch against the checklist, then try to refute each finding',
  whenToUse: 'Flow step 4 for a large task, once the owning agent reports part A green. args: {repo, branch, base?, ticket?, spec?, outcome?, tier?}',
  phases: [
    { title: 'Review', detail: 'one architect per group of checklist items, on Sonnet unless tier is hard' },
    { title: 'Verify', detail: 'one architect on Sonnet per finding, trying to refute it', model: 'sonnet' },
  ],
}

// args: { repo, branch, base = 'main', ticket?: 'KEY-n', spec?: 'paths or sections the diff implements',
//         outcome?: 'the outcome block (goal, outcome, criteria O1…)', tier?: 'normal' | 'hard' (default: normal) }
const ROOT = '{{ROOT}}'
const { repo, branch } = args || {}
const base = (args && args.base) || 'main'
// Model tiers (AGENTS.md): reviewers run on Sonnet for a normal-tier task, on the architect's Opus for a hard one.
const reviewModel = args && args.tier === 'hard' ? {} : { model: 'sonnet' }
if (!repo || !branch) throw new Error('args needs repo and branch')

const CONTEXT = `Workspace root: ${ROOT}. Repo: ${ROOT}/${repo}. Branch: ${branch}, base origin/${base}.${args.ticket ? ` Ticket: ${args.ticket}.` : ''}
${args.spec ? `Spec the diff implements: ${args.spec}.` : 'Find the spec and the decisions the diff cites (see the repo guide in AGENTS.md for where they live).'}
${args.outcome ? `Outcome the diff must meet:\n${args.outcome}` : 'The outcome and its criteria are in the PR body draft or the brief; if none is given, report the *Outcome met* checklist item as failed.'}
The checklist is ${ROOT}/.orchestrator/pre-pr-checklist.md. Start from \`git -C ${ROOT}/${repo} diff --stat origin/${base}...${branch}\`, then open only the files that carry risk for your items.
Read-only: never edit, commit, branch or push. Review as the human reviewer would: report only defects that break a checklist item, not style preferences.`

// The checklist's part B (the flow) and part C (quality, as this workspace adapted it). An item that names the
// repos it covers applies only to those.
const GROUPS = [
  { key: 'flow', items: 'in part B (contract line by line, repo rules and workspace standards, outcome met, test first when TDD is on)' },
  { key: 'quality', items: 'in part C, every one of them' },
]

const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          item: { type: 'integer', description: 'checklist item number' },
          file: { type: 'string', description: 'repo-relative path' },
          line: { type: 'integer' },
          summary: { type: 'string', description: 'one line: what is wrong and what the rule or spec says' },
        },
        required: ['item', 'file', 'summary'],
      },
    },
  },
  required: ['findings'],
}

const VERDICT = {
  type: 'object',
  properties: {
    refuted: { type: 'boolean' },
    reason: { type: 'string', description: 'one line' },
  },
  required: ['refuted', 'reason'],
}

const MAX_VERIFY = 8

const results = await pipeline(
  GROUPS,
  g => agent(`${CONTEXT}\n\nCheck the checklist items ${g.items} against this branch's diff. Return every failure, or an empty list.`,
    { label: `review:${g.key}`, phase: 'Review', agentType: 'architect', ...reviewModel, effort: 'medium', schema: FINDINGS }),
  (r, g) => {
    const found = (r && r.findings) || []
    if (found.length > MAX_VERIFY) log(`${g.key}: ${found.length} findings, verifying the first ${MAX_VERIFY}; the rest are reported unverified`)
    return parallel(found.map((f, i) => () => i >= MAX_VERIFY
      ? Promise.resolve({ ...f, verified: false })
      : agent(`${CONTEXT}\n\nA reviewer claims this branch fails checklist item ${f.item}: ${f.file}${f.line ? `:${f.line}` : ''}: ${f.summary}\nTry to refute it: read the code and the spec or rule it cites. Set refuted=true if the claim is wrong, already handled, or not what the item asks. If uncertain, refuted=false.`,
          { label: `verify:${f.file}`, phase: 'Verify', agentType: 'architect', model: 'sonnet', effort: 'medium', schema: VERDICT })
          .then(v => (v && !v.refuted ? { ...f, verified: true } : null))))
  },
)

const failures = results.flat().filter(Boolean)
return failures.length ? { result: 'FAIL', failures } : { result: 'PASS', failures: [] }
