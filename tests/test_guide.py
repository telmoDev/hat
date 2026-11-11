"""Tests for G4: the global guide, project rules template and agents built from templates/ (scripts/build_guide.py).
  python3 -m unittest tests.test_guide
"""
import hermetic  # noqa: F401  (first: never the real hat home)
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GUIDE = os.path.join(REPO, "guide")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


class Guide(unittest.TestCase):
    def test_the_committed_guide_is_what_the_template_builds(self):
        # templates/AGENTS.md stays the one source: editing it without rebuilding fails here.
        p = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "build_guide.py"), "--check"],
                           capture_output=True, encoding="utf-8")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_no_per_workspace_layout_is_left(self):
        for name in ("AGENTS.md", "agents/hat-explorer.md", "agents/hat-architect.md", "agents/hat-dev.md"):
            text = read(GUIDE, name)
            for old in ("{{", "TODO(orchestrator-setup)", ".orchestrator/", "`memory/", "`.agents/skills",
                        "sync-skills", "workspace", "{{ROOT}}", "odd/tasks", "under Layout", "root's skills", "``CODEX"):
                self.assertNotIn(old, text, "%s still has %r" % (name, old))

    def test_paths_point_at_the_state_folder_and_the_clone(self):
        text = read(GUIDE, "AGENTS.md")
        for path in ("<state>/memory/NEXT_STEPS.md", "<state>/tasks/<feature>.md", "<state>/config",
                     "<state>/rules.md", "<hat>/templates/orchestrator/scripts/push-pr.sh"):
            self.assertIn(path, text)

    def test_the_project_sections_are_in_the_rules_template_not_in_the_guide(self):
        guide, rules = read(GUIDE, "AGENTS.md"), read(GUIDE, "rules.md")
        for title in ("Commands", "Repo guides", "How the repos connect", "Rules"):
            self.assertIn("\n## %s\n" % title, rules)
        for title in ("Layout", "Commands", "Repo guides", "How the repos connect", "Workspace rules"):
            self.assertNotIn("\n## %s\n" % title, guide)

    def test_every_tool_mapping_reference_has_its_row(self):
        text = read(GUIDE, "AGENTS.md")
        mapping = text.split("## Tool mapping", 1)[1]
        for row in re.findall(r"\*Tool mapping\* › \*([^*]+)\*", text):
            self.assertIn("| %s" % row, mapping)

    def test_the_rules_did_not_change(self):
        # Same flow: every step, size and tier rule of the template is still in the guide.
        guide = read(GUIDE, "AGENTS.md")
        for rule in ("**Answers to the user.**", "**Ask or change.**", "**Size.**", "1. **Outcome and scope.**",
                     "4. **Review and pre-PR gate.**", "**Resume.**", "**Model tiers.**",
                     "**Read narrowly, delegate broadly.**", "**Delegate by context size.**"):
            self.assertIn(rule, guide)
        self.assertLessEqual(len(guide.split()), len(read(REPO, "templates", "AGENTS.md").split()))


class Skills(unittest.TestCase):
    def test_every_skill_has_a_global_version_without_workspace_paths(self):
        names = sorted(os.listdir(os.path.join(REPO, "templates", "skills")))
        self.assertEqual(sorted(os.listdir(os.path.join(GUIDE, "skills"))), names)
        for name in names:
            text = read(GUIDE, "skills", name, "SKILL.md")
            for old in ("{{", ".orchestrator/", "odd/", "workspace", ".claude/workflows"):
                self.assertNotIn(old, text, "%s still has %r" % (name, old))

    def test_the_guide_reads_skills_by_path_from_their_global_versions(self):
        text = read(GUIDE, "AGENTS.md")
        self.assertIn("<hat>/guide/skills/<name>/SKILL.md", text)
        self.assertNotIn("<hat>/templates/skills/", text)

    def test_sync_memory_commits_through_hat(self):
        self.assertIn("hat.py commit", read(GUIDE, "skills", "sync-memory", "SKILL.md"))


class Agents(unittest.TestCase):
    def test_three_global_agents_with_hat_names(self):
        self.assertEqual(sorted(os.listdir(os.path.join(GUIDE, "agents"))),
                         ["hat-architect.md", "hat-dev.md", "hat-explorer.md"])
        for name in ("hat-architect", "hat-dev", "hat-explorer"):
            self.assertIn("\nname: %s\n" % name, read(GUIDE, "agents", name + ".md"))

    def test_the_standards_digest_is_the_templates(self):
        def digest(text):
            return re.search(r"Standards digest[^\n]*\n((?:- [^\n]*\n)+)", text).group(1)
        self.assertEqual(digest(read(GUIDE, "agents", "hat-dev.md")),
                         digest(read(REPO, "templates", "agents", "developer.md")))

    def test_the_dev_agent_takes_its_repo_from_the_brief(self):
        text = read(GUIDE, "agents", "hat-dev.md")
        self.assertIn("the one repository the brief names", text)
        self.assertIn("<state>/rules.md", text)


if __name__ == "__main__":
    unittest.main()
