"""Unit tests for T7: the API-equivalent cost, always an estimate, never a subscription's spend.
  python3 -m unittest discover -s tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "templates", "orchestrator", "scripts")
sys.path.insert(0, SCRIPTS)
import api_cost as ac  # noqa: E402
import telemetry as t  # noqa: E402

# Made-up figures for the tests: no real price is assumed anywhere.
RATE = {"provider": "anthropic", "model": "model-a", "currency": "USD", "input": "3", "output": "15",
        "cache_read": "0.30", "cache_write": "3.75", "effective_from": "2026-01-01",
        "source": "https://example.invalid/pricing"}


def rates_file(d, rates, version="test-1"):
    p = os.path.join(d, "rates.json")
    with open(p, "w") as f:
        json.dump({"version": version, "rates": rates}, f)
    return p


class Rates(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_the_template_ships_no_prices(self):
        with open(os.path.join(os.path.dirname(SCRIPTS), "rates.json")) as f:
            self.assertEqual(json.load(f)["rates"], [])

    def test_missing_file_means_no_rates(self):
        rates, version, errors = ac.load_rates(os.path.join(self.dir, "nope.json"))
        self.assertEqual((rates, errors), ([], []))

    def test_invalid_entries_are_dropped_with_a_reason(self):
        bad = [dict(RATE, input="-1"), dict(RATE, effective_from="soon"), {k: v for k, v in RATE.items()
                                                                           if k != "source"}]
        rates, _, errors = ac.load_rates(rates_file(self.dir, bad + [RATE]))
        self.assertEqual((len(rates), len(errors)), (1, 3))

    def test_the_rate_in_force_on_the_day_applies(self):
        later = dict(RATE, input="4", effective_from="2026-06-01")
        rates, _, _ = ac.load_rates(rates_file(self.dir, [RATE, later]))
        self.assertEqual(ac.rate_for(rates, "anthropic", "model-a", "2026-05-31")["input"], Decimal("3"))
        self.assertEqual(ac.rate_for(rates, "anthropic", "model-a", "2026-06-01")["input"], Decimal("4"))
        self.assertIsNone(ac.rate_for(rates, "anthropic", "model-a", "2025-12-31"))
        self.assertIsNone(ac.rate_for(rates, "anthropic", "model-b", "2026-05-31"))


class Estimate(unittest.TestCase):
    def setUp(self):
        self.rate = ac.parse_rate(RATE)

    def usage(self, **kw):
        u = {"input_tokens": 1000, "output_tokens": 2000, "cache_read_tokens": 100000, "cache_write_tokens": 10000,
             "source": "runtime_reported"}
        u.update(kw)
        return u

    def test_anthropic_by_hand(self):
        # 1000*3 + 2000*15 + 100000*0.30 + 10000*3.75 = 3000 + 30000 + 30000 + 37500 = 100500 per million
        self.assertEqual(ac.estimate("claude-code", self.usage(), self.rate), (Decimal("0.1005"), None))

    def test_no_figures_no_cost(self):
        for name, u, rate in (("unavailable usage", self.usage(source="unavailable", input_tokens=None), self.rate),
                              ("estimated usage", self.usage(source="estimated"), self.rate),
                              ("no rate", self.usage(), None)):
            with self.subTest(name):
                cost, reason = ac.estimate("claude-code", u, rate)
                self.assertIsNone(cost)
                self.assertTrue(reason)

    def test_a_runtime_without_a_verified_rule_is_unavailable(self):
        # Codex reports cached input inside input_tokens: no rule until its real figures are checked.
        cost, reason = ac.estimate("codex", self.usage(), self.rate)
        self.assertIsNone(cost)
        self.assertIn("codex", reason)


class Report(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.s = t.Store(os.path.join(self.dir, "t.db"))

    def tearDown(self):
        self.s.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def agent(self, inv, model, source="runtime_reported", at="2026-03-01T10:00:00Z", **tokens):
        self.s.record(t.make_event("run.started", "claude:s1", timestamp=at, payload={"runtime": "claude-code"}))
        self.s.record(t.make_event("agent.started", "claude:s1", invocation_id=inv, timestamp=at,
                                   payload={"agent_type": "api-dev", "runtime": "claude-code", "model": model}))
        p = {"source": source, "model": model}
        if source != "unavailable":
            p.update({"input_tokens": 1000, "output_tokens": 2000, "cache_read_tokens": 100000,
                      "cache_write_tokens": 10000}, **tokens)
        self.s.record(t.make_event("usage.reported", "claude:s1", invocation_id=inv, timestamp=at, key=model,
                                   payload=p))

    def test_markdown_is_labelled_an_estimate_and_never_spend(self):
        self.agent("claude:a1", "model-a")
        self.agent("claude:a2", "model-b")
        self.agent("claude:a3", "model-a", source="unavailable")
        out = ac.report(self.s.db, rates_file(self.dir, [RATE]))
        self.assertIn("API-equivalent (estimated)", out)
        self.assertIn("not what a subscription", out)
        self.assertIn("5-minute and 1-hour", out)
        self.assertIn("| model-a | 2 | 1 | USD 0.1005 | test-1 · from 2026-01-01 · https://example.invalid/pricing |",
                      out)
        self.assertIn("| model-b | 1 | 0 | — | no rate for this model |", out)

    def test_no_rates_says_so(self):
        self.agent("claude:a1", "model-a")
        out = ac.report(self.s.db, rates_file(self.dir, []))
        self.assertIn("No rates", out)
        self.assertNotIn("USD", out)

    def test_cli(self):
        self.agent("claude:a1", "model-a")
        self.s.close()
        env = dict(os.environ, ORCH_TELEMETRY_DB=os.path.join(self.dir, "t.db"),
                   ORCH_RATES=rates_file(self.dir, [RATE]))
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "telemetry.py"), "cost"], capture_output=True,
                           env=env, timeout=60)
        self.s = t.Store(os.path.join(self.dir, "t.db"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(b"USD 0.1005", p.stdout)

    def test_benchmark_10k_invocations_under_300_ms(self):
        db = self.s.db
        db.execute("BEGIN")
        for i in range(10000):
            db.execute("INSERT INTO agent_invocations (invocation_id, run_id, runtime, model, started_at) "
                       "VALUES (?, 'claude:s1', 'claude-code', 'model-a', '2026-03-01T10:00:00.000Z')", ("i%d" % i,))
            db.execute("INSERT INTO usage_records (usage_id, invocation_id, run_id, model, input_tokens, output_tokens,"
                       " cache_read_tokens, cache_write_tokens, source) VALUES (?, ?, 'claude:s1', 'model-a', 1000, "
                       "2000, 100000, 10000, 'runtime_reported')", ("u%d" % i, "i%d" % i))
        db.execute("COMMIT")
        path = rates_file(self.dir, [RATE])
        start = time.perf_counter()
        out = ac.report(db, path)
        ms = (time.perf_counter() - start) * 1000
        print("\nbenchmark T7: API-equivalent estimate over 10,000 invocations %.0f ms" % ms)
        self.assertIn("USD 1005.0000", out)  # 10,000 x 0.1005, exact in Decimal
        self.assertLess(ms, 300)


if __name__ == "__main__":
    unittest.main()
