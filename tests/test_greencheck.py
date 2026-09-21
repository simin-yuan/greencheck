"""Tests for greencheck.

    python -m unittest discover -s tests -v

No third-party dependencies on purpose: anyone should be able to check the
claims without installing anything.
"""

import contextlib
import io
import json
import os
import pathlib
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from greencheck import cli  # noqa: E402
from greencheck import mutate  # noqa: E402
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
        # Ask the product where its skills are, rather than assuming a path.
        # The assumption is what broke when the skills moved into the package;
        # the assertion we actually want is "the CLI can find them".
        cls.root = cli._skills_root()
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


class TestMutationOperators(unittest.TestCase):
    """Every operator must have an input it is *known* to fire on.

    This is the product's own rule applied to the product. An operator that has
    never been observed to produce a mutant is not an operator, it is a function
    nobody calls.

    The JSON case below is not hypothetical. `blank-value` silently produced
    *zero* mutants on a JSON file for as long as its pattern expected `key: value`
    and JSON writes `"key": "value"`. It looked like coverage. It was a string.
    """

    JSON = '{\n  "service": "billing",\n  "replicas": 3\n}\n'
    YAML = "service: billing\nreplicas: 3\n"
    MD = "# Title\n\n## Alpha\nalpha body\n\n## Beta\nbeta body\n"

    def _fire(self, op, files):
        out = list(op(files))
        self.assertTrue(out, f"{op.__name__} produced no mutants on this input")
        return out

    def test_drop_file_fires(self):
        self._fire(mutate.op_drop_file, {"a.json": self.JSON})

    def test_empty_file_fires(self):
        self._fire(mutate.op_empty_file, {"a.json": self.JSON})

    def test_drop_section_fires_on_markdown(self):
        out = self._fire(mutate.op_drop_section, {"a.md": self.MD})
        self.assertTrue(any("Alpha" in n for n, _ in out))

    def test_drop_line_fires(self):
        self._fire(mutate.op_drop_line, {"a.json": self.JSON})

    def test_blank_value_fires_on_json_with_quoted_keys(self):
        out = self._fire(mutate.op_blank_value, {"a.json": self.JSON})
        names = [n for n, _ in out]
        self.assertTrue(any("service" in n for n in names), names)
        self.assertTrue(any("replicas" in n for n in names), names)

    def test_blank_value_fires_on_yaml(self):
        self.assertTrue(len(self._fire(mutate.op_blank_value, {"a.yaml": self.YAML})) >= 2)

    def test_blank_value_keeps_the_document_parsable(self):
        """A mutant that breaks JSON syntax tests the parser, not the gate.

        Numbers must stay numbers and booleans must stay booleans: blanking
        `"replicas": 3` to `"replicas":` produces unparsable JSON, and the gate
        then rejects it for the wrong reason.
        """
        for name, patch in mutate.op_blank_value({"a.json": self.JSON}):
            with self.subTest(mutant=name):
                json.loads(patch["a.json"])  # must not raise

    def test_blank_value_preserves_scalar_types(self):
        src = '{\n  "name": "svc",\n  "n": 3,\n  "on": true\n}\n'
        got = {n: p["a.json"] for n, p in mutate.op_blank_value({"a.json": src})}
        self.assertIn('"name": ""', got['blank-value:a.json:2:"name":'])
        self.assertIn('"n": 0', got['blank-value:a.json:3:"n":'])
        self.assertIn('"on": false', got['blank-value:a.json:4:"on":'])

    def test_break_reference_fires(self):
        self._fire(mutate.op_break_reference, {"a.md": "see FOO-BAR-01 for detail\n"})

    def test_dup_id_fires(self):
        self._fire(mutate.op_dup_id, {"a.md": self.MD})

    def test_no_registered_operator_is_dead_code(self):
        """The blanket version: nothing in OPERATORS may be unreachable.

        The corpus has to contain the *shape* each operator needs. An operator
        that finds nothing here is either dead code or starved of input, and
        those two look identical from the outside — so give it input.
        """
        corpus = {
            "a.json": self.JSON,                              # quoted keys, numbers
            "b.md": self.MD,                                  # headings, sections
            "c.yaml": self.YAML,                              # bare keys
            "d.md": "# Index\n\nsee FOO-BAR-01 for detail\n",  # a reference id
        }
        for op in mutate.OPERATORS:
            with self.subTest(op=op.__name__):
                self._fire(op, corpus)

    def test_build_mutants_deduplicates(self):
        corpus = {"a.json": self.JSON}
        mutants = mutate.build_mutants(corpus)
        names = [n for n, _ in mutants]
        self.assertEqual(len(names), len(set(names)))


class TestVersionIsSingleSourced(unittest.TestCase):
    def test_package_version_matches_pyproject(self):
        """One version, one place.

        The package reported 0.1.0 while pyproject said 0.2.0 — a second copy of
        a fact that had already drifted. Two numbers, at least one of them wrong,
        which is the exact shape of the problem this tool exists to find.
        """
        import re

        from greencheck import __version__

        root = pathlib.Path(__file__).resolve().parent.parent
        declared = re.search(
            r'^version\s*=\s*"([^"]+)"',
            (root / "pyproject.toml").read_text(encoding="utf-8"),
            re.M,
        ).group(1)
        self.assertEqual(__version__, declared)


if __name__ == "__main__":
    unittest.main()
