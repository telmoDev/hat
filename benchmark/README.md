# Benchmark

Fixed tasks on a fixed fixture, to measure the orchestrator's flows with the same instrument. Manual and on demand:
nothing here calls a model except `run`, and only when you run it. Each run spends your plan's quota; measure a
pilot before deciding how many runs to make.

- `fixture/`: two small repos with no dependencies. `api/` (Python 3.8+ standard library, `unittest`) has a seeded
  bug between `cart` and `pricing`; `web/` (JavaScript modules, `node --test`, Node 18+).
- `tasks/B1…B5.md`: each task's request, given verbatim to the session, and its criteria.

  | Task | Kind | Checked by |
  |---|---|---|
  | B1 | explore how a cart total is computed | the answer's JSON facts against the code: functions, three totals, how often the coupon comes off |
  | B2 | add `GET /products/<id>` | hidden tests, and the repo's tests |
  | B3 | fix the coupon applied twice | hidden tests, and the repo's tests |
  | B4 | a cart badge on the page | hidden `node` tests, the page's header, and the repo's tests (`blocked` without Node) |
  | B5 | one price-formatting function | the formatting written once, the same outputs as before (a probe over prices, summaries and `GET /products`), and the repo's tests |

- `checks/`: the acceptance tests and the probe, copied in only when checking, never seen by the session.
- `solutions/`: a reference solution per task, used by `tests/test_benchmark.py` to prove each task can be solved
  and its checks tell a right result from a wrong one.
- `results/`: the result files of real runs (see its README).

## A run

```bash
python3 scripts/benchmark.py prepare B1 v0.7.0 /tmp/b1-old    # or: current
python3 scripts/benchmark.py run /tmp/b1-old --model <model>   # the only step that uses a model; --model required
python3 scripts/benchmark.py result /tmp/b1-old --label pilot-v0.7.0
```

`prepare` copies the fixture, scaffolds the flow (`current` from this checkout, `v0.7.0` from its tag) and installs
the same measurement layer in both: the current telemetry scripts and hooks. Only the flow under test differs.
`run` gives the session the task's request on stdin (`claude -p`, edits accepted, only python, node and git allowed;
no push), and saves its final answer to `.bench/answer.md`. A session can also be run by hand in the workspace (for
B1, save the answer there), but it has no named model, so its result is never compared. `result` runs the checks on a copy of the workspace, reads its telemetry and writes the
result JSON. Files consulted are recorded as `unavailable`: no hook reports them.

## Comparing

```bash
python3 templates/orchestrator/scripts/telemetry.py benchmark benchmark/results/<A> benchmark/results/<B>
```

Runs are compared only with the same task hash (request and criteria, hidden checks, fixture, the harness code that
grades the task, and the session's settings), runtime and named models; a run without a named model or with a
`blocked` criterion (B4 without Node) isn't either. Anything else is "not comparable". Quality and consumption are shown apart, each as n, median and range; a quality regression (any mandatory
criterion passing less often, or more failing tests) is never read as an efficiency gain, overlapping ranges show no difference, tokens with incomplete coverage aren't
compared, and fewer than 3 runs on a side is flagged. Wall time and cumulative agent time are kept apart.
