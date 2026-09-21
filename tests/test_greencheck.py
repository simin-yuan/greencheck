"""Tests for greencheck.

    python -m unittest discover -s tests -v

No third-party dependencies on purpose: anyone should be able to check the
claims without installing anything.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


if __name__ == "__main__":
    unittest.main()
