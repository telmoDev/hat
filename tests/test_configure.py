"""Tests for G5 (roadmap X4): what differs per project is configuration, so no project has to fork a layer file.
  python3 -m unittest tests.test_configure
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as f:
        return f.read()


def layer_files():
    for base in ("templates", "guide"):
        for d, _, files in os.walk(os.path.join(REPO, base)):
            for name in files:
                if name != "pre-pr-checklist.md" and name.endswith((".md", ".sh", ".py", ".js", ".conf")):
                    yield os.path.join(d, name)


class Configure(unittest.TestCase):
    def test_no_file_cites_a_checklist_item_by_number(self):
        # A project with its own checklist numbers its items its own way: cite an item by its title.
        for path in layer_files():
            with open(path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    self.assertIsNone(re.search(r"\bitems? \d+\b", line),
                                      "%s:%d cites a checklist item by number: %s" % (path, n, line.strip()))

    def test_the_test_first_and_outcome_items_are_cited_by_title(self):
        self.assertIn("*Test first*", read("templates", "orchestrator", "scripts", "pre-pr-pass.sh"))
        self.assertIn("*Outcome met*", read("templates", "skills", "pre-pr-review", "SKILL.md"))
        self.assertIn("*Outcome met*", read("templates", "claude", "workflows", "pre-pr-review.js"))

    def test_the_ticket_system_is_configuration(self):
        conf = read("templates", "orchestrator", "orchestrator.conf")
        self.assertRegex(conf, r'(?m)^TICKETS=""$')
        self.assertRegex(conf, r'(?m)^TICKET_PROJECT=""$')
        for text in (read("templates", "AGENTS.md"), read("guide", "AGENTS.md")):
            self.assertIn("**Tickets.**", text)
            self.assertIn("`TICKETS`", text)
        self.assertIn("`TICKETS`", read("templates", "skills", "sync-memory", "SKILL.md"))


if __name__ == "__main__":
    unittest.main()
