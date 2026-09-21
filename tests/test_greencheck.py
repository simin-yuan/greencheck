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
import re
import subprocess
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


class TestPublishedNumbersAreCheckable(unittest.TestCase):
    """A headline a reader cannot recompute is the defect this package reports.

    The first version of this repository led with a larger figure: events
    recorded before the guard's first firing, counted by timestamp. Reproducing
    it needs event-level data, and only aggregates are published -- so the
    published daily rows summed to a smaller number, and anyone who tried to
    check the claim would have found the arithmetic did not agree.

    The same story told in whole days is checkable with a for-loop. These tests
    keep it that way.
    """

    def setUp(self):
        self.root = pathlib.Path(__file__).resolve().parent.parent
        self.daily = [
            json.loads(line)
            for line in (self.root / "data/gate_daily.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        self.summary = json.loads(
            (self.root / "data/gate_summary.json").read_text(encoding="utf-8")
        )

    def _zero_days(self):
        first_day = self.summary["first_fire_utc"][:10]
        return [r for r in self.daily if r["date"] < first_day and r["firings"] == 0]

    def test_headline_equals_sum_of_published_rows(self):
        """The headline has to come out of gate_daily.jsonl, and nothing else."""
        rows = self._zero_days()
        self.assertEqual(
            sum(r["events"] for r in rows), self.summary["events_in_zero_firing_days"]
        )
        self.assertEqual(
            len(rows), self.summary["days_with_zero_firings_before_first_fire"]
        )

    def test_breakdown_equals_sum_of_published_rows(self):
        rows = self._zero_days()
        for kind, claimed in self.summary["event_totals_in_zero_firing_days"].items():
            got = sum(r.get("by_event", {}).get(kind, 0) for r in rows)
            self.assertEqual(got, claimed, f"{kind} does not match the daily rows")

    def test_no_document_quotes_the_uncheckable_figure(self):
        """If it cannot be recomputed from data/, it does not belong in a document."""
        banned = ("28,176", "28176", "26,668", "26668")
        docs = [
            self.root / "README.md",
            self.root / "case_study/results/CASE_STUDY.md",
            self.root / "case_study/results/tables.json",
        ] + sorted((self.root / "greencheck/skills").glob("*/SKILL.md"))
        for path in docs:
            text = path.read_text(encoding="utf-8")
            for token in banned:
                self.assertNotIn(
                    token, text,
                    f"{path.name} quotes {token}, which a reader cannot recompute from data/",
                )

    def test_history_of_the_correction_is_kept(self):
        """The superseded figure stays in the summary so the change is auditable."""
        self.assertEqual(self.summary["events_before_first_fire"], 28176)
        self.assertGreater(
            self.summary["events_before_first_fire"],
            self.summary["events_in_zero_firing_days"],
        )


class TestReportDoesNotPublishTheOperator(unittest.TestCase):
    """A report is a file people commit, paste into issues and attach to bugs.

    The first version recorded the absolute target path, so the ordinary act of
    running the demo committed the operator's username and directory layout into
    the repository. A tool whose subject is "was this actually checked" should
    not widen what leaves the machine while it runs.
    """

    def setUp(self):
        self.root = pathlib.Path(__file__).resolve().parent.parent

    def test_recorded_target_is_relative(self):
        from greencheck.mutate import _portable

        here = pathlib.Path.cwd()
        got = _portable(here / "examples" / "mutate-demo" / "input")
        self.assertFalse(os.path.isabs(got), f"absolute path recorded: {got}")
        self.assertNotIn(":\\", got)
        self.assertNotIn(":/", got)

    def test_no_examples_report_carries_a_machine_path(self):
        """If such a file is ever committed again, this goes red."""
        pattern = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]")
        for path in (self.root / "examples").rglob("*.json"):
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertIsNone(
                pattern.search(text),
                f"{path.relative_to(self.root)} contains what looks like a local path",
            )


class TestTheLicenceIsComplete(unittest.TestCase):
    """The licence shipped truncated at 453 bytes: title, copyright, opening clause.

    GitHub read it as NOASSERTION, which is GitHub's way of saying "this is not a
    licence I recognise". The missing half held the disclaimer.

    A project whose subject is that an artefact must be checked before it is
    trusted shipped an unchecked artefact. The check is cheap, so it is a test.
    """

    def setUp(self):
        self.root = pathlib.Path(__file__).resolve().parent.parent

    def test_mit_licence_contains_its_operative_clauses(self):
        text = (self.root / "LICENSE").read_text(encoding="utf-8")
        for needed in (
            "Permission is hereby granted",
            "WITHOUT WARRANTY OF ANY KIND",
            "MERCHANTABILITY",
            "LIABILITY",
        ):
            self.assertIn(needed, text, f"LICENSE is missing: {needed}")

    def test_licence_is_the_length_of_the_real_thing(self):
        """Standard MIT is ~1070 bytes. Truncation was how this went wrong."""
        size = (self.root / "LICENSE").stat().st_size
        self.assertGreater(size, 1000, f"LICENSE is only {size} bytes — truncated?")


class TestEveryCommandInTheReadmeActuallyRuns(unittest.TestCase):
    """A README command that does not run is the first thing a reader hits.

    Three of them did not: two invoked a validate.py and a ./config that exist
    nowhere in the repository, and the gate example pointed at a real file with
    the wrong schema and printed a number that disagreed with the README by
    1,079. For a package whose whole subject is that a claim must be checked,
    shipping unchecked commands in the first screen is the defect itself.
    """

    def setUp(self):
        self.root = pathlib.Path(__file__).resolve().parent.parent
        self.readme = (self.root / "README.md").read_text(encoding="utf-8")

    def _shell_commands(self):
        """Every `$ ...` line inside a fenced block, minus two kinds.

        Skipped on purpose:
        - `pip install`, which needs the network;
        - `unittest`, which would re-enter this suite from inside itself.
        """
        out = []
        for line in self.readme.splitlines():
            stripped = line.strip()
            if stripped.startswith("$ "):
                cmd = stripped[2:].strip()
                if cmd.startswith("pip install"):
                    continue
                if "unittest" in cmd:
                    continue
                out.append(cmd)
        return out

    def test_there_are_commands_to_check(self):
        self.assertGreaterEqual(len(self._shell_commands()), 3)

    def test_each_one_exits_zero(self):
        for cmd in self._shell_commands():
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=str(self.root),
                capture_output=True,
                text=True,
                # The CLI prints em-dashes and the odd non-ASCII glyph. On
                # Windows the child's stdout is not UTF-8 by default, and a
                # strict decode raises inside subprocess's reader thread, which
                # surfaces as noise rather than as a test failure.
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            # `gate` on a log with a dead gate returns 1 by design, so a
            # non-zero status is only a failure when nothing explains it.
            self.assertIn(
                proc.returncode,
                (0, 1),
                f"README command exited {proc.returncode}: {cmd}\n"
                f"stdout: {stdout[-600:]}\nstderr: {stderr[-600:]}",
            )
            self.assertNotIn(
                "Traceback",
                stderr,
                f"README command raised: {cmd}\n{stderr[-800:]}",
            )

    def test_no_command_points_at_a_file_that_does_not_exist(self):
        """The specific way they were broken: plausible paths, absent files."""
        known_absent = ("validate.py", "./config ", "guard_events.jsonl", " ledger.jsonl")
        for cmd in self._shell_commands():
            for ghost in known_absent:
                self.assertNotIn(
                    ghost,
                    cmd,
                    f"README command references {ghost!r}, which is not in the repo: {cmd}",
                )

    def test_the_documented_test_count_is_the_real_one(self):
        """The README said '13 tests' while the suite ran 41.

        Counted, not run. Running the suite from inside the suite would
        re-enter this class and re-run every README command recursively.
        """
        counts = re.findall(r"#\s*(\d+)\s+tests", self.readme)
        if not counts:
            self.skipTest("the README no longer quotes a test count")
        suite = unittest.defaultTestLoader.discover(str(self.root / "tests"))
        actual = suite.countTestCases()
        for quoted in counts:
            self.assertEqual(
                int(quoted),
                actual,
                f"README quotes {quoted} tests; the suite contains {actual}",
            )


if __name__ == "__main__":
    unittest.main()
