"""docs/telemetry.md matches the contract in code, and each F1 criterion is traceable to its evidence.
  python3 -m unittest tests.test_telemetry_doc
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "templates", "orchestrator", "scripts"))
import claude_transcript  # noqa: E402
import telemetry  # noqa: E402

DOC = os.path.join(ROOT, "docs", "telemetry.md")


def section(text, heading):
    """The body of the '## <heading>' section, up to the next '## '."""
    m = re.search(r"^## %s\n(.*?)(?=^## |\Z)" % re.escape(heading), text, re.M | re.S)
    if not m:
        raise AssertionError("no '## %s' section" % heading)
    return m.group(1)


def rows(body):
    """Table rows as lists of cells, header and separator dropped."""
    out = [[c.strip() for c in line.strip().strip("|").split("|")] for line in body.splitlines()
           if line.strip().startswith("|")]
    return [r for r in out[1:] if not set("".join(r)) <= set("-: ")]


def codes(cell):
    return set(re.findall(r"`([^`]+)`", cell))


class Doc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(DOC, encoding="utf-8") as f:
            cls.text = f.read()

    def test_every_event_type_and_its_payload_keys(self):
        table = {codes(r[0]).pop(): r for r in rows(section(self.text, "Events")) if codes(r[0])}
        self.assertEqual(set(table), set(telemetry.EVENTS))
        for kind, (needs_inv, allowed) in telemetry.EVENTS.items():
            self.assertEqual(table[kind][1].lower(), "yes" if needs_inv else "no", kind)
            self.assertEqual(codes(table[kind][2]), set(allowed), kind)

    def test_statuses(self):
        table = {r[0]: codes(r[1]) for r in rows(section(self.text, "Statuses"))}
        self.assertEqual(table, {k: set(v) for k, v in telemetry.STATUSES.items()})

    def test_sources_tokens_and_versions(self):
        body = section(self.text, "Figures and their sources")
        self.assertEqual({s for s in telemetry.SOURCES if "`%s`" % s in body}, set(telemetry.SOURCES))
        self.assertEqual({t for t in telemetry.TOKENS if "`%s`" % t in body}, set(telemetry.TOKENS))
        self.assertIn("Event schema version: %d" % telemetry.SCHEMA_VERSION, self.text)
        self.assertIn("Store migrations: %d" % max(v for v, _ in telemetry.MIGRATIONS), self.text)
        self.assertIn("`%s`" % claude_transcript.PARSER_VERSION, self.text)
        self.assertIn("%d characters" % telemetry.MAX_STR, self.text)

    def test_every_table_of_the_store(self):
        tables = set(re.findall(r"CREATE TABLE (\w+)", "".join(sql for _, sql in telemetry.MIGRATIONS)))
        body = section(self.text, "Store")
        self.assertEqual({t for t in tables if "`%s`" % t in body}, tables)

    def test_settings(self):
        body = section(self.text, "Settings")
        for key in ("TELEMETRY", "TELEMETRY_TRANSCRIPTS", "ORCH_TELEMETRY_DB", "ORCH_RATES"):
            self.assertIn("`%s`" % key, body)

    def test_every_f1_criterion_has_its_evidence(self):
        table = {r[0]: r for r in rows(section(self.text, "F1 acceptance criteria"))}
        self.assertEqual(sorted(table), ["F1-%02d" % n for n in range(1, 15)])
        for cid, r in table.items():
            evidence, state = r[2], r[3]
            self.assertIn(state, ("verified", "partial", "not met"), cid)
            refs = re.findall(r"`(tests/[\w./]+) › (\w+)`", evidence)
            if not refs:
                self.assertRegex(evidence, r"^(manual|smoke|not met): \S", cid + " names no test, check or reason")
            for path, name in refs:
                with open(os.path.join(ROOT, path), encoding="utf-8") as f:
                    self.assertRegex(f.read(), r"def %s\(" % name, "%s cites a missing test %s" % (cid, name))


if __name__ == "__main__":
    unittest.main()
