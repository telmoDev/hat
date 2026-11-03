# Benchmark results

One JSON file per run, written by `python3 scripts/benchmark.py result <workspace> --label <label>` into
`results/<label>/`. Versioned as evidence. A result holds ids, versions, criteria statuses, test counts and
telemetry figures only: never a prompt, an answer, source code, a path or a transcript. SQLite stores and logs are
never committed here.

Compare two labels with `python3 templates/orchestrator/scripts/telemetry.py benchmark results/<A> results/<B>`
(or `.orchestrator/scripts/telemetry.py` in a workspace).
