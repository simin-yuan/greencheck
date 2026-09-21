"""Tests for greencheck.

    python -m unittest discover -s tests -v

No third-party dependencies on purpose: anyone should be able to check the
claims without installing anything.
"""

import contextlib
import io
import os
import pathlib
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from greencheck import cli  # noqa: E402
from greencheck import (  # noqa: E402
    BARE_ZERO,
    CONSTANT,
    DEAD_GATE,
    IDENTITY,
    LIVENESS_BIT,
    ProbePair,
    audit_gate_counts,
    audit_ledger,
    discriminate,
)


class TestDiscriminate(unittest.TestCase):
    def setUp(self):
        self.pairs = [
            ProbePair("rich vs degenerate", "the quick brown fox", "aaaa", dimension="content"),
            ProbePair("present vs absent", "hello", "", dimension="presence"),
        ]

    def test_healthy_instrument_passes(self):
        r = discriminate(len, self.pairs, subject="len", claimed_dimensions=["content"])
        self.assertTrue(r.ok, r.verdicts)

    def test_constant_instrument_is_flagged(self):
        r = discriminate(lambda x: 1.0, self.pairs, subject="one", claimed_dimensions=["content"])
        self.assertIn(IDENTITY, r.verdicts)

    def test_instrument_that_only_sees_existence_is_flagged_for_content(self):
        """The important case: it separates *something*, so a naive
        'did any two outputs differ' check would let it through."""
        fn = lambda x: 1.0 if x else 0.0  # noqa: E731
        r = discriminate(fn, self.pairs, subject="presence", claimed_dimensions=["content"])
        self.assertIn(IDENTITY, r.verdicts)
        self.assertEqual(r.stats["pairs_separated"], 1, "it does separate the presence pair")
        self.assertEqual(r.stats["separated_by_dimension"]["content"], 0)

    def test_same_instrument_passes_for_the_dimension_it_actually_measures(self):
        fn = lambda x: 1.0 if x else 0.0  # noqa: E731
        r = discriminate(fn, self.pairs, subject="presence", claimed_dimensions=["presence"])
        self.assertTrue(r.ok, r.verdicts)


class TestAuditLedger(unittest.TestCase):
    def test_constant_over_window(self):
        rows = [{"v": 1.0} for _ in range(10)]
        r = audit_ledger(rows, "v", "const")
        self.assertIn(CONSTANT, r.verdicts)
        self.assertEqual(r.stats["distinct_values"], 1)

    def test_bare_zero_requires_a_count_field(self):
        rows = [{"v": 0.0, "n": 0}, {"v": 0.0, "n": 0}, {"v": 0.0, "n": 8}]
        r = audit_ledger(rows, "v", "recall", count_field="n")
        self.assertIn(BARE_ZERO, r.verdicts)

    def test_no_bare_zero_when_zero_never_occurs(self):
        rows = [{"v": 0.5, "n": 3}, {"v": 0.7, "n": 8}]
        r = audit_ledger(rows, "v", "recall", count_field="n")
        self.assertNotIn(BARE_ZERO, r.verdicts)

    def test_liveness_bit(self):
        rows = [{"v": 0.7, "f": True} for _ in range(5)]
        rows += [{"v": 0.55, "f": False} for _ in range(5)]
        r = audit_ledger(rows, "v", "overall", fresh_field="f")
        self.assertIn(LIVENESS_BIT, r.verdicts)
        self.assertEqual(r.stats["variance_explained_by"]["f"], 1.0)

    def test_liveness_bit_not_reported_when_fresh_is_not_uniformly_predictive(self):
        rows = [{"v": 1.0, "f": True}, {"v": 1.0, "f": True}, {"v": 0.5, "f": False}, {"v": 1.0, "f": False}]
        r = audit_ledger(rows, "v", "overall", fresh_field="f")
        self.assertNotIn(LIVENESS_BIT, r.verdicts)

    def test_empty_ledger_does_not_crash(self):
        r = audit_ledger([], "v", "empty")
        self.assertIn("NO_DATA", r.verdicts)


class TestAuditGate(unittest.TestCase):
    def test_zero_firings_is_dead_gate(self):
        r = audit_gate_counts(total_events=28176, firings=0, health_events=26668, subject="gate")
        self.assertIn(DEAD_GATE, r.verdicts)
        self.assertFalse(r.ok)

    def test_firings_pass(self):
        r = audit_gate_counts(total_events=33210, firings=5, health_events=31613, subject="gate")
        self.assertTrue(r.ok, r.verdicts)

    def test_empty_window_is_not_evidence_of_death(self):
        r = audit_gate_counts(total_events=0, firings=0, subject="gate")
        self.assertNotIn(DEAD_GATE, r.verdicts)


class TestSkills(unittest.TestCase):
    """The skills are part of the product, so they get verified like any other
    artefact.

    A skill with a malformed header is worse than a missing one: the harness
    loads it and gets nothing, and nothing is what a silent failure looks like.
    """

    @classmethod
    def setUpClass(cls):
        cls.root = pathlib.Path(__file__).resolve().parent.parent / "skills"
        cls.skills = sorted(p for p in cls.root.iterdir() if (p / "SKILL.md").is_file())

    def _frontmatter(self, path):
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---"), f"{path} has no frontmatter")
        end = text.find("\n---", 3)
        self.assertNotEqual(end, -1, f"{path} has unclosed frontmatter")
        block = {}
        for line in text[3:end].splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                block[key.strip().lower()] = value.strip()
        return block

    def test_at_least_five_skills_ship(self):
        self.assertGreaterEqual(len(self.skills), 5)

    def test_every_skill_declares_name_and_description(self):
        for p in self.skills:
            fm = self._frontmatter(p / "SKILL.md")
            self.assertIn("name", fm, p.name)
            self.assertIn("description", fm, p.name)

    def test_declared_name_matches_its_directory(self):
        for p in self.skills:
            fm = self._frontmatter(p / "SKILL.md")
            self.assertEqual(fm["name"], p.name)

    def test_description_states_its_trigger(self):
        """A description that does not say *when* to load the skill does not get
        loaded. 'Use when ...' is the contract with the harness."""
        for p in self.skills:
            fm = self._frontmatter(p / "SKILL.md")
            self.assertTrue(
                fm["description"].startswith("Use when"),
                f"{p.name}: description must start with 'Use when'",
            )

    def test_cli_lists_every_skill(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli.main(["skills"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        for p in self.skills:
            self.assertIn(p.name, out)

    def test_cli_prints_a_skill_in_full(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli.main(["skills", "positive-control"])
        self.assertEqual(rc, 0)
        self.assertIn("## The rule", buf.getvalue())

    def test_cli_rejects_an_unknown_skill_name(self):
        with contextlib.redirect_stderr(io.StringIO()):
            rc = cli.main(["skills", "no-such-skill-exists"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
