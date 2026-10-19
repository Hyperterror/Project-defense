#!/usr/bin/env python3
"""
test_scoring.py -- Tests for scripts/score_report.py.

Verifies:
  - weights sum to 1.0
  - all-correct input yields score 1.0
  - all-zero input yields score 0.0
  - partial scores produce correct weighted result
  - output is deterministic (same input = same output twice)
  - output validates against assessment-result.schema.json structure
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import score_report as sr


def _make_session(questions):
    """Build a minimal session dict from a list of question dicts."""
    return {
        "session_id": "sess-test0001",
        "session_identity": "abc123",
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
        "mode": "assessment",
        "status": "completed",
        "questions": questions,
        "coding_results": [],
        "summary": None,
    }


def _q(question_id, category, scores):
    """Build a question entry with given per-concept scores."""
    return {
        "question_id": question_id,
        "rubric_id": "test-rubric",
        "answer": "some answer",
        "scores": scores,
        "category": category,
    }


class TestScoring(unittest.TestCase):
    def test_weights_sum_to_one(self):
        total = round(sum(sr.CATEGORY_WEIGHTS.values()), 10)
        self.assertEqual(total, 1.0, f"Weights must sum to 1.0, got {total}")

    def test_all_correct_yields_one(self):
        """Every concept scored 3 across ALL 6 categories -> overall_score == 1.0."""
        questions = [
            _q("q-e001", "explanation", {"request-lifecycle": 3, "jwt-generation": 3}),
            _q("q-c001", "core_implementation", {"impl": 3, "edge-cases": 3}),
            _q("q-c002", "independent_coding", {"impl": 3, "tests": 3}),
            _q("q-f001", "failure_scenario", {"crash-vs-retry": 3, "graceful-degradation": 3}),
            _q("q-t001", "trade_off", {"document-model-fit": 3, "scalability-claims": 3}),
            _q("q-s001", "security", {"input-validation": 3, "secrets": 3}),
        ]
        session = _make_session(questions)
        result = sr.compute_scores(session)
        self.assertAlmostEqual(result["overall_score"], 1.0, places=5,
                               msg=f"All-3 input across all 6 categories should give 1.0, got {result['overall_score']}")

    def test_all_zero_yields_zero(self):
        """Every concept scored 0 -> overall_score == 0.0."""
        questions = [
            _q("q-e001", "explanation", {"request-lifecycle": 0, "jwt-generation": 0}),
            _q("q-f001", "failure_scenario", {"crash-vs-retry": 0, "graceful-degradation": 0}),
        ]
        session = _make_session(questions)
        result = sr.compute_scores(session)
        self.assertEqual(result["overall_score"], 0.0,
                         f"All-0 input should give 0.0, got {result['overall_score']}")

    def test_partial_scores_weighted(self):
        """Hand-computed weighted result for a known set."""
        # explanation -> Architecture (0.15)
        #   concepts avg = (3 + 1) / 2 / 3 = 0.6667
        # coding_task -> Independent Coding (0.30)
        #   concepts avg = (2 + 0) / 2 / 3 = 0.3333
        # Architecture contributes 0.6667 * 0.15 = 0.10
        # Independent Coding contributes 0.3333 * 0.30 = 0.10
        # expected overall = 0.20
        questions = [
            _q("q-e001", "explanation", {"request-lifecycle": 3, "jwt-generation": 1}),
            _q("q-c001", "coding_task", {"implementation": 2, "edge-cases": 0}),
        ]
        session = _make_session(questions)
        result = sr.compute_scores(session)
        expected = ( (3 + 1) / 2 / 3 ) * 0.15 + ( (2 + 0) / 2 / 3 ) * 0.30
        self.assertAlmostEqual(result["overall_score"], expected, places=4,
                              msg=f"Expected {expected}, got {result['overall_score']}")

    def test_deterministic(self):
        """Same input gives identical output (excluding generated_at)."""
        questions = [
            _q("q-e001", "explanation", {"a": 2, "b": 3}),
            _q("q-f001", "failure_scenario", {"x": 1}),
        ]
        session = _make_session(questions)
        r1 = sr.compute_scores(session)
        r2 = sr.compute_scores(session)
        # Compare everything except generated_at (timestamp)
        r1_cmp = {k: v for k, v in r1.items() if k != "generated_at"}
        r2_cmp = {k: v for k, v in r2.items() if k != "generated_at"}
        self.assertEqual(r1_cmp, r2_cmp, "Output should be deterministic")

    def test_validates_against_schema_structure(self):
        """Output must have the structure required by assessment-result.schema.json."""
        schema_path = SKILL_DIR / "templates" / "assessment-result.schema.json"
        questions = [
            _q("q-e001", "explanation", {"a": 2}),
        ]
        session = _make_session(questions)
        result = sr.compute_scores(session)

        # Check required fields are present
        for field in ("session_id", "overall_score", "categories", "strengths", "gaps", "generated_at"):
            self.assertIn(field, result, f"Missing required field: {field}")

        # overall_score must be 0.0-1.0
        self.assertGreaterEqual(result["overall_score"], 0.0)
        self.assertLessEqual(result["overall_score"], 1.0)

        # If schema exists, validate using validate_graph
        if schema_path.exists():
            sys.path.insert(0, str(SCRIPTS_DIR))
            try:
                from validate_graph import validate_value
                schema = json.loads(schema_path.read_text())
                # Merge score fields into a session-shaped object for validation
                merged = dict(session)
                merged.update(result)
                errors = validate_value(merged, schema, schema)
                self.assertEqual(len(errors), 0,
                                 f"Schema validation errors: {errors}")
            except ImportError:
                pass  # skip if validate_graph unavailable


if __name__ == "__main__":
    unittest.main(verbosity=2)
