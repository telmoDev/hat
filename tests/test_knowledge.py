"""Tests for K1: the native OKF v0.2 validator and indexer (templates/orchestrator/scripts/knowledge.py).
  python3 -m unittest tests.test_knowledge
Fixtures follow the shapes of the OKF v0.2 spec (GoogleCloudPlatform/knowledge-catalog, okf/SPEC.md), written
here, not copied. No network, no model.
"""
import hermetic  # noqa: F401  (first: never the real hat home)
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SCRIPTS = os.path.join(REPO, "templates", "orchestrator", "scripts")
sys.path.insert(0, SCRIPTS)
import knowledge as k  # noqa: E402

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

ROOT_INDEX = '---\nokf_version: "0.2"\n---\n\n# Payments knowledge\n\nHand-written intro stays.\n'
DECISION = """---
type: Decision
title: Coupons apply before tax
description: The coupon discount is taken from the subtotal, before tax is added.
tags: [checkout, pricing]
status: stable
sources:
  - id: adr-7
    resource: /references/adr-007.md
    title: ADR 7
    author: human:telmo
    last_modified: 2026-10-30T12:00:00Z
  - id: pr-143
    resource: https://example.invalid/org/api/pull/143
usage_window: { from: 2026-10-01T00:00:00Z, to: 2026-10-31T00:00:00Z }
generated: { by: hat/0.8.0, at: 2026-11-06T10:00:00Z }
verified:
  - { by: human:telmo, at: 2026-11-06T11:00:00+01:00 }
  - { by: process:memory-check, at: 2026-11-06T11:05:00Z }
stale_after: 2027-05-01T00:00:00Z
x_scope: project
x_origin_project: payments
owner_note: "kept: unknown keys are fine"
---

# Decision

Coupons apply to the subtotal.[^adr-7] The order total is computed in `Cart.total`.[^pr-143]

See [checkout flow](/flows/checkout.md) and [the reference](../references/adr-007.md).

[^adr-7]: ADR 7
[^pr-143]: PR 143
"""
FLOW = """---
type: Playbook
title: Checkout flow
description: How an order goes from cart to payment.
verified: { by: human:telmo, at: 2026-11-06T11:00:00Z }
---

# Steps

1. Cart, 2. coupon, 3. payment.
"""
REFERENCE = "---\ntype: Reference\ntitle: ADR 7\n---\n\nThe original record.\n"
LOG = "# Update log\n\n## 2026-11-06\n* **Creation**: first export.\n"
LEGACY = """---
type: Metric
title: Revenue
timestamp: 2026-06-01T00:00:00Z
---

# Definition

Sum of order totals.

# Citations

- Finance handbook
"""


class Bundle(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.write("index.md", ROOT_INDEX)
        self.write("log.md", LOG)
        self.write("decisions/coupons-before-tax.md", DECISION)
        self.write("flows/checkout.md", FLOW)
        self.write("references/adr-007.md", REFERENCE)

    def write(self, rel, text):
        p = os.path.join(self.dir, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def read(self, rel):
        with open(os.path.join(self.dir, *rel.split("/")), encoding="utf-8") as f:
            return f.read()

    def findings(self):
        return k.validate(self.dir)

    def errors(self):
        return [f for f in self.findings() if f[0] == "error"]

    def warnings(self):
        return [f for f in self.findings() if f[0] == "warning"]

    def assertOneError(self, rel, words):
        errs = self.errors()
        self.assertEqual(len(errs), 1, errs)
        self.assertEqual(errs[0][1], rel)
        self.assertIn(words, errs[0][2])


class Validate(Bundle):
    def test_a_v02_bundle_is_clean(self):
        self.assertEqual(self.findings(), [])

    def test_v01_concepts_are_accepted_with_legacy_warnings(self):
        self.write("metrics/revenue.md", LEGACY)
        self.assertEqual(self.errors(), [])
        msgs = " ".join(w[2] for w in self.warnings())
        self.assertIn("legacy v0.1 `timestamp`", msgs)
        self.assertIn("legacy v0.1 `# Citations`", msgs)

    def test_conformance_is_permissive(self):
        self.write("misc/thing.md", "---\ntype: Something Nobody Registered\nanything: [1, 2]\n---\n"
                                    "[missing](/nowhere.md)\n")
        self.assertEqual(self.errors(), [])
        self.assertEqual([w[2] for w in self.warnings()], ["broken link: /nowhere.md"])

    def test_no_frontmatter(self):
        self.write("notes/loose.md", "# Just text\n")
        self.assertOneError("notes/loose.md", "no frontmatter")

    def test_no_type(self):
        self.write("notes/untyped.md", "---\ntitle: Untyped\n---\n")
        self.assertOneError("notes/untyped.md", "`type`")

    def test_frontmatter_only_on_the_root_index(self):
        self.write("flows/index.md", "---\ntype: Index\n---\n# Flows\n")
        self.assertOneError("flows/index.md", "only the bundle-root index.md")

    def test_timestamps_need_an_offset(self):
        self.write("flows/checkout.md", FLOW.replace("2026-11-06T11:00:00Z", "2026-11-06T11:00:00"))
        self.assertOneError("flows/checkout.md", "verified[0].at")

    def test_actors(self):
        self.write("flows/checkout.md", FLOW.replace("human:telmo", "telmo"))
        self.assertOneError("flows/checkout.md", "verified[0].by")

    def test_generated_needs_by(self):
        self.write("decisions/coupons-before-tax.md",
                   DECISION.replace("generated: { by: hat/0.8.0, at:", "generated: { at:"))
        self.assertOneError("decisions/coupons-before-tax.md", "generated.by")

    def test_a_source_needs_a_resource(self):
        self.write("decisions/coupons-before-tax.md",
                   DECISION.replace("    resource: https://example.invalid/org/api/pull/143\n", "    title: PR\n"))
        self.assertOneError("decisions/coupons-before-tax.md", "sources[1].resource")

    def test_status_is_lifecycle(self):
        self.write("flows/checkout.md", FLOW.replace("type: Playbook", "type: Playbook\nstatus: established"))
        self.assertOneError("flows/checkout.md", "`status`")

    def test_scope(self):
        self.write("decisions/coupons-before-tax.md", DECISION.replace("x_scope: project", "x_scope: everyone"))
        self.assertOneError("decisions/coupons-before-tax.md", "`x_scope`")

    def test_log_dates(self):
        self.write("log.md", LOG.replace("## 2026-11-06", "## Nov 6"))
        self.assertOneError("log.md", "YYYY-MM-DD")

    def test_secrets_are_errors_and_never_quoted(self):
        self.write("flows/checkout.md", FLOW + "\napi_key: sk-live-abcdef0123456789\n")
        self.assertOneError("flows/checkout.md", "line 12")
        self.assertNotIn("sk-live", " ".join(map(str, self.findings())))

    def test_a_long_url_is_not_a_secret_but_a_token_in_its_query_is(self):  # seen in the OKF sample bundles
        url = "https://meta.example.invalid/questions/2677/database-schema-documentation-for-the-public-data-dump"
        self.write("flows/checkout.md", FLOW + "\nFrom [the schema](%s).\n" % url)
        self.assertEqual(self.errors(), [])
        self.write("flows/checkout.md", FLOW + "\nSee https://example.invalid/x?token=abcdef123456\n")
        self.assertOneError("flows/checkout.md", "line 12")

    def test_a_footnote_without_its_source(self):
        self.write("decisions/coupons-before-tax.md", DECISION.replace(".[^pr-143]\n", ".[^pr-999]\n"))
        self.assertEqual(self.errors(), [])
        self.assertIn("footnote [^pr-999] has no sources entry", [w[2] for w in self.warnings()])

    def test_okf_version(self):
        self.write("index.md", ROOT_INDEX.replace('"0.2"', '"0.1"'))
        self.assertEqual(self.errors(), [])
        self.assertIn('okf_version is "0.1": this validator targets 0.2', [w[2] for w in self.warnings()])

    def test_unsupported_yaml_is_an_error_not_a_crash(self):
        self.write("flows/checkout.md", "---\ntype: Playbook\nnotes: |\n  multi\n  line\n---\n")
        if HAVE_YAML:
            self.assertEqual(self.errors(), [])
        else:
            self.assertOneError("flows/checkout.md", "YAML")


class Parser(unittest.TestCase):
    def test_the_subset_reads_every_shape_in_the_fixtures(self):
        for text in (DECISION, FLOW, REFERENCE, LEGACY):
            fm, _ = k.split_frontmatter(text)
            data = k.load_yaml(fm, subset=True)
            self.assertIsInstance(data, dict)
        data = k.load_yaml(k.split_frontmatter(DECISION)[0], subset=True)
        self.assertEqual(data["tags"], ["checkout", "pricing"])
        self.assertEqual(data["sources"][0]["author"], "human:telmo")
        self.assertEqual(data["generated"], {"by": "hat/0.8.0", "at": "2026-11-06T10:00:00Z"})
        self.assertEqual(data["verified"][0]["at"], "2026-11-06T11:00:00+01:00")
        self.assertEqual(data["usage_window"]["to"], "2026-10-31T00:00:00Z")
        self.assertEqual(data["owner_note"], "kept: unknown keys are fine")

    def test_folded_plain_scalars(self):  # PyYAML's own dumps wrap long values like this
        fm = "type: Table\ndescription: All blocks, including headers,\n  counts, sizes, and timestamps.\ntags:\n- a\n"
        self.assertEqual(k.load_yaml(fm, subset=True), {"type": "Table", "tags": ["a"],
                         "description": "All blocks, including headers, counts, sizes, and timestamps."})

    @unittest.skipUnless(HAVE_YAML, "PyYAML not installed")
    def test_the_subset_agrees_with_pyyaml(self):
        for text in (DECISION, FLOW, REFERENCE, LEGACY):
            fm, _ = k.split_frontmatter(text)
            self.assertEqual(k.load_yaml(fm, subset=True), k.load_yaml(fm, subset=False))


class Index(Bundle):
    def test_generates_listings_and_keeps_what_is_hand_written(self):
        concepts = {r: hashlib.sha256(self.read(r).encode()).hexdigest()
                    for r in ("decisions/coupons-before-tax.md", "flows/checkout.md", "references/adr-007.md")}
        changed = k.index(self.dir)
        self.assertEqual(sorted(changed), ["decisions/index.md", "flows/index.md", "index.md", "references/index.md"])
        root = self.read("index.md")
        self.assertTrue(root.startswith('---\nokf_version: "0.2"\n---\n'))
        self.assertIn("Hand-written intro stays.", root)
        self.assertIn("* [decisions](decisions/)", root)
        flows = self.read("flows/index.md")
        self.assertIn("# Playbook", flows)
        self.assertIn("* [Checkout flow](/flows/checkout.md) - How an order goes from cart to payment.", flows)
        for r, digest in concepts.items():  # concepts (and their unknown keys) are never rewritten
            self.assertEqual(hashlib.sha256(self.read(r).encode()).hexdigest(), digest, r)
        self.assertEqual(k.index(self.dir), [])  # a second run changes nothing
        self.assertEqual(k.validate(self.dir), [])

    def test_hand_edits_outside_the_block_survive_a_rerun(self):
        k.index(self.dir)
        self.write("flows/index.md", "# Flows\n\nMy note.\n\n" + self.read("flows/index.md"))
        self.write("flows/refund.md", FLOW.replace("Checkout flow", "Refund flow"))
        self.assertEqual(k.index(self.dir), ["flows/index.md"])
        flows = self.read("flows/index.md")
        self.assertTrue(flows.startswith("# Flows\n\nMy note.\n"))
        self.assertIn("[Refund flow](/flows/refund.md)", flows)


class Cli(Bundle):
    def run_cli(self, *args):
        py = shutil.which("python3") or shutil.which("python")
        return subprocess.run([py, os.path.join(SCRIPTS, "knowledge.py")] + list(args), capture_output=True,
                              encoding="utf-8", timeout=30)

    def test_validate_exit_codes(self):
        p = self.run_cli("validate", self.dir)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("0 error(s), 0 warning(s)", p.stdout)
        self.write("notes/loose.md", "# Just text\n")
        p = self.run_cli("validate", self.dir)
        self.assertEqual(p.returncode, 1)
        self.assertIn("error: notes/loose.md:", p.stdout)

    def test_index_cli(self):
        p = self.run_cli("index", self.dir)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("wrote flows/index.md", p.stdout)

    def test_no_network_or_model(self):
        with open(os.path.join(SCRIPTS, "knowledge.py"), encoding="utf-8") as f:
            src = f.read()
        for word in ("socket", "urllib", "http.client", "requests", "anthropic", "subprocess"):
            self.assertNotIn(word, src)


if __name__ == "__main__":
    unittest.main()
