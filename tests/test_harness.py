"""Tests for X2: the harness capability contract (templates/orchestrator/scripts/harness.py).
  python3 -m unittest tests.test_harness
No runtime is launched: health checks run stub binaries that only answer --version.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SCRIPTS = os.path.join(REPO, "templates", "orchestrator", "scripts")
sys.path.insert(0, SCRIPTS)
import harness  # noqa: E402

DOC = os.path.join(REPO, "docs", "harnesses.md")


def stub_bin(folder, name, version, log):
    """A fake CLI that records its arguments and answers --version only."""
    path = os.path.join(folder, name)
    with open(path, "w", newline="\n") as f:
        f.write('#!/usr/bin/env bash\necho "$@" >> "%s"\n[ "$1" = --version ] && echo "%s" && exit 0\nexit 9\n'
                % (log.replace("\\", "/"), version))
    os.chmod(path, 0o755)


class Contract(unittest.TestCase):
    def test_every_adapter_declares_every_capability(self):
        self.assertEqual(set(harness.ADAPTERS), {"claude-code", "codex"})
        for runtime, a in harness.ADAPTERS.items():
            self.assertEqual(set(a["capabilities"]), set(harness.CAPABILITIES), runtime)
            for name, (status, how) in a["capabilities"].items():
                self.assertIn(status, harness.STATUSES, (runtime, name))
                self.assertTrue(how.strip(), (runtime, name))

    def test_codex_claims_nothing_verified(self):
        caps = harness.ADAPTERS["codex"]["capabilities"]
        self.assertNotIn("verified", {status for status, _ in caps.values()})

    def test_claude_events_and_usage_are_the_verified_ones(self):
        caps = harness.ADAPTERS["claude-code"]["capabilities"]
        self.assertEqual({n for n, (s, _) in caps.items() if s == "verified"},
                         {"health_check", "collect_events", "usage"})

    def test_the_doc_matches_the_code(self):
        with open(DOC, encoding="utf-8") as f:
            text = f.read()
        rows = [[c.strip() for c in line.strip().strip("|").split("|")] for line in text.splitlines()
                if line.startswith("| `")]
        table = {}
        for r in rows:
            m = re.match(r"`(\w+)`", r[0])
            table[m.group(1)] = (r[1], r[2])
        self.assertEqual(set(table), set(harness.CAPABILITIES))
        for name, (claude, codex) in table.items():
            self.assertTrue(claude.startswith(harness.ADAPTERS["claude-code"]["capabilities"][name][0]), name)
            self.assertTrue(codex.startswith(harness.ADAPTERS["codex"]["capabilities"][name][0]), name)


class Health(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ws = os.path.join(self.tmp, "ws")
        for d in (".claude", ".codex"):
            os.makedirs(os.path.join(self.ws, d))
        shutil.copy(os.path.join(REPO, "templates", "claude", "settings.json"), os.path.join(self.ws, ".claude"))
        shutil.copy(os.path.join(REPO, "templates", "codex", "hooks.json"), os.path.join(self.ws, ".codex"))
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        self.log = os.path.join(self.tmp, "calls.log")

    def env(self):
        sep = ";" if os.name == "nt" else ":"
        bash = os.path.dirname(shutil.which("bash"))
        return dict(os.environ, PATH=sep.join([self.bin, bash, "/usr/bin", "/bin"]))

    def test_installed_and_configured(self):
        stub_bin(self.bin, "claude", "9.9.9 (Claude Code)", self.log)
        h = harness.health_check("claude-code", self.ws, env=self.env())
        self.assertTrue(h["installed"])
        self.assertEqual(h["version"], "9.9.9 (Claude Code)")
        self.assertTrue(h["configured"], h["missing"])
        with open(self.log) as f:
            self.assertEqual(f.read().split(), ["--version"])  # nothing but the version is ever asked

    def test_a_missing_hook_is_named(self):
        stub_bin(self.bin, "claude", "9.9.9", self.log)
        p = os.path.join(self.ws, ".claude", "settings.json")
        with open(p) as f:
            s = json.load(f)
        s["hooks"]["SessionEnd"][0]["hooks"] = [h for h in s["hooks"]["SessionEnd"][0]["hooks"]
                                                if "session-handoff" not in h["command"]]
        with open(p, "w") as f:
            json.dump(s, f)
        h = harness.health_check("claude-code", self.ws, env=self.env())
        self.assertFalse(h["configured"])
        self.assertEqual(h["missing"], ["SessionEnd: session-handoff.sh end"])

    def test_not_installed_is_reported_not_raised(self):
        h = harness.health_check("codex", self.ws, env=self.env())
        self.assertEqual((h["installed"], h["version"]), (False, None))
        self.assertTrue(h["configured"], h["missing"])

    def test_a_workspace_without_the_tool_is_not_configured(self):
        shutil.rmtree(os.path.join(self.ws, ".codex"))
        h = harness.health_check("codex", self.ws, env=self.env())
        self.assertFalse(h["configured"])
        self.assertEqual(h["missing"], [".codex/hooks.json"])

    def test_doctor(self):
        stub_bin(self.bin, "claude", "9.9.9 (Claude Code)", self.log)
        scripts = os.path.join(self.ws, ".orchestrator", "scripts")
        os.makedirs(scripts)
        shutil.copy(os.path.join(SCRIPTS, "harness.py"), scripts)
        py = shutil.which("python3") or shutil.which("python")
        p = subprocess.run([py, os.path.join(scripts, "harness.py"), "doctor"], capture_output=True, env=self.env(),
                           encoding="utf-8", timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("claude-code: installed 9.9.9 (Claude Code) · configured", p.stdout)
        self.assertIn("codex: not installed · configured", p.stdout)
        self.assertIn("| `collect_events` | verified", p.stdout)
        p = subprocess.run([py, os.path.join(scripts, "harness.py"), "doctor", "--json"], capture_output=True,
                           env=self.env(), encoding="utf-8", timeout=30)
        data = json.loads(p.stdout)
        self.assertEqual(data["codex"]["capabilities"]["usage"]["status"], "unverified")

    def test_no_network_or_model(self):
        with open(os.path.join(SCRIPTS, "harness.py"), encoding="utf-8") as f:
            src = f.read()
        for word in ("socket", "urllib", "http", "anthropic", '"-p"', '"exec"'):
            self.assertNotIn(word, src)


if __name__ == "__main__":
    unittest.main()
