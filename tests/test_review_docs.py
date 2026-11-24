#!/usr/bin/env python3
"""
test_review_docs.py -- Tests for the study-loop and repository-integrity tools.

Covered:
  - check_docs.py flags broken links, unmentioned scripts, duplicate rubric ids
  - the shipped repository passes its own documentation lint
  - plan_review.py schedules unanswered questions immediately
  - a weak question comes back sooner than a strong one
  - the plan interleaves categories instead of blocking them
  - rubric selection prefers a topic-matched fallback over the generic one

Run: python3 -m unittest discover -s tests -p "test_*.py"
"""

import datetime as dt
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import check_docs  # noqa: E402
import generate_question_bank as gqb  # noqa: E402
import plan_review  # noqa: E402
import score_report  # noqa: E402


def check_docs_sorted_weights():
    return sorted(score_report.CATEGORY_WEIGHTS.items())


class TestDocIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-docs-"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, rel, text):
        path = self.tmpdir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_shipped_repository_is_clean(self):
        problems = check_docs.check(SKILL_DIR)
        self.assertEqual(problems, [], "\n".join(problems))

    def test_score_weights_must_match_the_scorer(self):
        """Rounding the weights in prose is a real bug: the agent quotes them."""
        self._write("instructions/02-generate-docs.md",
                    "- Architecture: 15%\n- Coding: 25%\n")
        problems = []
        check_docs.check_score_weights(self.tmpdir, problems)
        self.assertEqual(len(problems), 5, "\n".join(problems))
        self.assertTrue(
            any("Independent Coding: 30%" in p for p in problems), problems
        )

    def test_matching_score_weights_pass(self):
        weights = "".join(
            "- %s: %d%%\n" % (cat, round(w * 100))
            for cat, w in check_docs_sorted_weights()
        )
        self._write("instructions/02-generate-docs.md", weights)
        problems = []
        check_docs.check_score_weights(self.tmpdir, problems)
        self.assertEqual(problems, [])

    def test_broken_link_is_reported(self):
        self._write("SKILL.md", "---\nname: demo\ndescription: Demo skill.\n---\n\n"
                                "See [the guide](./instructions/missing.md).\n")
        problems = check_docs.check(self.tmpdir)
        self.assertTrue(any("broken link" in p for p in problems), problems)

    def test_missing_path_mention_is_reported(self):
        self._write("SKILL.md", "---\nname: demo\ndescription: Demo skill.\n---\n\n"
                                "Run `scripts/not_there.py` first.\n")
        problems = check_docs.check(self.tmpdir)
        self.assertTrue(any("missing path" in p for p in problems), problems)

    def test_unmentioned_script_is_dead_wiring(self):
        self._write("SKILL.md", "---\nname: demo\ndescription: Demo skill.\n---\n")
        self._write("scripts/orphan.py", "print('hi')\n")
        problems = check_docs.check(self.tmpdir)
        self.assertTrue(any("dead wiring" in p for p in problems), problems)

    def test_frontmatter_is_required(self):
        self._write("SKILL.md", "# No frontmatter here\n")
        problems = check_docs.check(self.tmpdir)
        self.assertTrue(any("frontmatter" in p for p in problems), problems)

    def test_duplicate_rubric_ids_are_reported(self):
        self._write("SKILL.md", "---\nname: demo\ndescription: Demo skill.\n---\n")
        rubric = '{"id": "same-id", "question_id": "generic", "max_score": 12}'
        self._write("rubrics/a.json", rubric)
        self._write("rubrics/b.json", rubric)
        problems = check_docs.check(self.tmpdir)
        self.assertTrue(any("duplicate id" in p for p in problems), problems)


def _write_bank(root, questions):
    defense = root / ".project-defense"
    defense.mkdir(parents=True, exist_ok=True)
    (defense / "question-bank.json").write_text(
        json.dumps({"questions": questions}), encoding="utf-8"
    )


def _write_session(root, name, updated_at, answered):
    sessions = root / ".project-defense" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / (name + ".json")).write_text(
        json.dumps({
            "session_id": name,
            "session_identity": "identity",
            "created_at": updated_at,
            "updated_at": updated_at,
            "mode": "strict",
            "status": "completed",
            "questions": answered,
            "coding_results": [],
        }),
        encoding="utf-8",
    )


class TestReviewPlan(unittest.TestCase):
    TODAY = dt.date(2026, 3, 10)

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-review-"))
        _write_bank(self.tmpdir, [
            {"id": "q-e001", "category": "explanation", "text": "Explain auth."},
            {"id": "q-e002", "category": "explanation", "text": "Explain routes."},
            {"id": "q-f001", "category": "failure_scenario", "text": "DB down?"},
            {"id": "q-c001", "category": "coding_task", "text": "Implement POST."},
        ])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _plan(self, limit=10):
        return plan_review.build_plan(self.tmpdir, self.TODAY, limit)

    def test_unanswered_questions_are_due_immediately(self):
        plan = self._plan()
        self.assertEqual(plan["due_count"], 4)
        reasons = {q["question_id"]: q["reason"] for q in plan["questions"]}
        self.assertEqual(reasons["q-c001"], "never answered")
        self.assertIsNone(plan["questions"][0]["mean_score"])

    def test_weak_question_returns_before_strong_one(self):
        _write_session(self.tmpdir, "sess-a", "2026-03-01T10:00:00+00:00", [
            {"question_id": "q-e001", "scores": {"a": 0, "b": 1}, "scored_by": "agent",
             "answered_at": "2026-03-01T10:00:00+00:00"},
            {"question_id": "q-f001", "scores": {"a": 3, "b": 3}, "scored_by": "agent",
             "answered_at": "2026-03-01T10:00:00+00:00"},
        ])
        plan = self._plan()
        by_id = {q["question_id"]: q for q in plan["questions"]}
        # The weak answer is reviewed early (1 day back), the strong one keeps the
        # first rung of the ladder (also 1 day) -- so both are due, but only the
        # weak one is labelled as such and carries its missing concepts.
        self.assertIn("weak", by_id["q-e001"]["reason"])
        self.assertEqual(by_id["q-e001"]["concept_gaps"], ["a", "b"])
        self.assertNotIn("weak", by_id["q-f001"]["reason"])

    def test_spacing_pushes_a_mastered_question_out(self):
        _write_session(self.tmpdir, "sess-a", "2026-03-01T10:00:00+00:00", [
            {"question_id": "q-e001", "scores": {"a": 3, "b": 3}, "scored_by": "agent",
             "answered_at": "2026-03-01T10:00:00+00:00"},
        ])
        _write_session(self.tmpdir, "sess-b", "2026-03-05T10:00:00+00:00", [
            {"question_id": "q-e001", "scores": {"a": 3, "b": 3}, "scored_by": "agent",
             "answered_at": "2026-03-05T10:00:00+00:00"},
        ])
        plan = self._plan()
        entry = next(q for q in plan["questions"] if q["question_id"] == "q-e001")
        due = dt.date.fromisoformat(entry["due"])
        self.assertGreaterEqual((due - dt.date(2026, 3, 5)).days, 3,
                                "a twice-mastered question must not be due the next day")

    def test_plan_interleaves_categories(self):
        _write_session(self.tmpdir, "sess-a", "2026-03-01T10:00:00+00:00", [
            {"question_id": "q-e001", "scores": {"a": 1}, "scored_by": "agent",
             "answered_at": "2026-03-01T10:00:00+00:00"},
            {"question_id": "q-e002", "scores": {"a": 1}, "scored_by": "agent",
             "answered_at": "2026-03-01T10:00:00+00:00"},
        ])
        plan = self._plan()
        categories = [q["category"] for q in plan["questions"]]
        self.assertGreater(len(set(categories)), 1)
        for first, second in zip(categories, categories[1:]):
            self.assertNotEqual(
                first, second,
                "two questions of the same category must not sit next to each other: %s"
                % categories,
            )

    def test_limit_is_respected(self):
        self.assertEqual(len(self._plan(limit=2)["questions"]), 2)

    def test_missing_bank_fails_loudly(self):
        empty = Path(tempfile.mkdtemp(prefix="pdc-review-empty-"))
        try:
            with self.assertRaises(SystemExit) as ctx:
                plan_review.build_plan(empty, self.TODAY)
            self.assertIn("no question bank", str(ctx.exception))
        finally:
            shutil.rmtree(empty, ignore_errors=True)


class TestRubricSelection(unittest.TestCase):
    def setUp(self):
        self.rubrics = gqb._load_rubrics()

    def test_topic_matched_fallback_wins(self):
        text = "If `authMiddleware` were deleted entirely, what would break?"
        self.assertEqual(
            gqb._rubric_for(self.rubrics, "q-e900", "explanation", text),
            "explanation-module-depth-v1",
        )

    def test_generic_fallback_still_applies(self):
        text = "Walk me through the `TodoItem` in `client/src/components/TodoItem.jsx`."
        self.assertEqual(
            gqb._rubric_for(self.rubrics, "q-e901", "explanation", text),
            "explanation-generic-v1",
        )

    def test_every_shipped_rubric_is_reachable(self):
        used = set()
        for key, candidates in self.rubrics.items():
            for rubric_id, _topics in candidates:
                used.add(rubric_id)
        shipped = {p.stem for p in (SKILL_DIR / "rubrics").glob("*.json")}
        self.assertTrue(shipped.issubset(used), shipped - used)


if __name__ == "__main__":
    unittest.main(verbosity=2)
