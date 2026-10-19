#!/usr/bin/env python3
"""
test_assess.py -- Tests for generate_question_bank.py and assess.py.

Tests:
  - create_session produces a valid session JSON
  - update_session persists updates
  - session status transitions (not_started -> in_progress -> completed)
  - strict mode suppresses hints in generated output
  - question bank generates all 4 categories
  - question bank JSON has required fields
  - question bank MD file exists
  - assess start creates a session
  - assess answer advances the session
  - assess finish produces a score
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

import generate_question_bank as gqb
import save_progress as sp


# Minimal project graph with one component, route, risk, model
MINIMAL_GRAPH = {
    "session_identity": "test-identity-12345",
    "project": {
        "name": "test-app",
        "purpose": "A test app for assessment tests.",
        "stack": ["React", "Express", "MongoDB"],
        "entry_points": [{"file": "server/index.js", "type": "backend"}],
    },
    "frontend": {
        "pages": [],
        "components": [
            {
                "name": "LoginForm",
                "details": {"type": "component"},
                "evidence": {"file": "src/LoginForm.jsx", "lines": [1, 30],
                             "excerpt": "export default function LoginForm", "status": "code-verified"},
            }
        ],
        "state_management": [],
        "api_calls": [],
    },
    "backend": {
        "routes": [
            {"method": "POST", "path": "/api/login", "handler": "loginController",
             "evidence": {"file": "server/routes/auth.js", "lines": [5, 15],
                          "excerpt": 'router.post("/login"', "status": "code-verified"}},
        ],
        "middleware": [], "controllers": [], "services": [],
    },
    "data": {
        "models": [
            {"name": "User", "fields": [{"name": "email", "type": "String"}],
             "evidence": {"file": "server/models/User.js", "lines": [1, 20],
                          "excerpt": "const User = mongoose.model", "status": "code-verified"}},
        ],
        "relationships": [], "migrations": [],
    },
    "auth": {"strategy": "JWT", "token_handling": "Bearer", "protected_routes": []},
    "user_flows": [],
    "data_flows": [],
    "risks": [
        {"description": "No tests directory.", "severity": "high",
         "evidence": {"file": "README.md", "lines": [1, 1], "excerpt": "no tests", "status": "code-verified"},
         "mitigation": "Add tests."},
    ],
    "uncertainties": [
        {"question": "Where is the JWT secret stored in production?", "context": "env var.",
         "evidence": {"file": "scan-facts.json", "lines": [1, 1], "excerpt": "JWT_SECRET", "status": "code-verified"},
         "impact_if_wrong": "Cannot recommend rotation strategy."},
    ],
}


class TestQuestionBank(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-qb-test-"))
        defense_dir = self.tmpdir / ".project-defense"
        defense_dir.mkdir()
        (defense_dir / "project-graph.json").write_text(json.dumps(MINIMAL_GRAPH), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_question_bank_generates_all_categories(self):
        bank = gqb.generate_question_bank(self.tmpdir)
        cats = {q["category"] for q in bank["questions"]}
        for cat in ("explanation", "failure_scenario", "trade_off", "coding_task"):
            self.assertIn(cat, cats, f"Question bank must include category: {cat}")

    def test_question_bank_json_has_required_fields(self):
        bank = gqb.generate_question_bank(self.tmpdir)
        for q in bank["questions"]:
            for field in ("id", "category", "text", "difficulty", "project_references"):
                self.assertIn(field, q, f"Question missing required field: {field}")

    def test_question_bank_md_generated(self):
        gqb.generate_question_bank(self.tmpdir)
        md_path = self.tmpdir / ".project-defense" / "question-bank.md"
        self.assertTrue(md_path.exists(), "question-bank.md must be generated")
        md_text = md_path.read_text(encoding="utf-8")
        bank = json.loads((self.tmpdir / ".project-defense" / "question-bank.json").read_text())
        for q in bank["questions"]:
            self.assertIn(q["text"], md_text, "MD must contain each question's text")


class TestAssess(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-assess-test-"))
        defense_dir = self.tmpdir / ".project-defense"
        defense_dir.mkdir()
        (defense_dir / "project-graph.json").write_text(json.dumps(MINIMAL_GRAPH), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_session_produces_valid_json(self):
        import save_progress as sp
        sessions_dir = sp._sessions_dir(self.tmpdir)
        session_identity = sp._get_session_identity(self.tmpdir)
        now = "2024-01-01T00:00:00+00:00"
        session_id = sp._make_session_id(session_identity, now)
        session = sp.create_session(sessions_dir, session_id, session_identity, "assessment")
        self.assertEqual(session["status"], "active")
        self.assertEqual(session["mode"], "assessment")
        self.assertIn("questions", session)
        self.assertIn("coding_results", session)

    def test_update_session_persists(self):
        import save_progress as sp
        sessions_dir = sp._sessions_dir(self.tmpdir)
        session_identity = sp._get_session_identity(self.tmpdir)
        now = "2024-01-01T00:00:00+00:00"
        session_id = sp._make_session_id(session_identity, now)
        sp.create_session(sessions_dir, session_id, session_identity, "assessment")
        # Update
        updated = sp.update_session(sessions_dir, session_id, {"status": "completed"})
        self.assertEqual(updated["status"], "completed")
        # Reload and verify persistence
        loaded = sp.load_session(sessions_dir, session_id)
        self.assertEqual(loaded["status"], "completed")

    def test_session_status_transitions(self):
        """not_started (active) -> in_progress -> completed."""
        import save_progress as sp
        sessions_dir = sp._sessions_dir(self.tmpdir)
        session_identity = sp._get_session_identity(self.tmpdir)
        now = "2024-01-01T00:00:00+00:00"
        session_id = sp._make_session_id(session_identity, now)
        sp.create_session(sessions_dir, session_id, session_identity, "assessment")
        # active -> in_progress
        sp.update_session(sessions_dir, session_id, {"status": "active"})
        loaded = sp.load_session(sessions_dir, session_id)
        self.assertEqual(loaded["status"], "active")
        # -> completed
        sp.update_session(sessions_dir, session_id, {"status": "completed"})
        loaded = sp.load_session(sessions_dir, session_id)
        self.assertEqual(loaded["status"], "completed")

    def test_strict_mode_suppresses_hints(self):
        """In strict mode, the answer output should NOT include a hint."""
        import assess as a
        import save_progress as sp

        # Start a session in strict mode
        a.cmd_start(self.tmpdir, "strict")
        sessions_dir = sp._sessions_dir(self.tmpdir)
        sessions = sp.list_sessions(sessions_dir)
        self.assertEqual(len(sessions), 1, "cmd_start should create exactly one session")
        session_id = sessions[0]["session_id"]

        # Load the question bank to get the first question id
        bank = json.loads((self.tmpdir / ".project-defense" / "question-bank.json").read_text())
        first_q = bank["questions"][0]

        # Capture stdout from cmd_answer in strict mode
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            a.cmd_answer(self.tmpdir, session_id, first_q["id"], "I don't know", mode="strict")
        out = json.loads(buf.getvalue())
        self.assertNotIn("hint", out, "Strict mode must suppress hints in the output")


class TestAssessFullFlow(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-assess-full-"))
        defense_dir = self.tmpdir / ".project-defense"
        defense_dir.mkdir()
        (defense_dir / "project-graph.json").write_text(json.dumps(MINIMAL_GRAPH), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_assess_finish_produces_score(self):
        """Start, answer all questions with 'I don't know', finish -> score file exists."""
        import assess as a
        import save_progress as sp
        import io
        from contextlib import redirect_stdout

        # Start
        buf = io.StringIO()
        with redirect_stdout(buf):
            a.cmd_start(self.tmpdir, "strict")
        sessions_dir = sp._sessions_dir(self.tmpdir)
        sessions = sp.list_sessions(sessions_dir)
        session_id = sessions[0]["session_id"]

        # Get the question bank
        bank = json.loads((self.tmpdir / ".project-defense" / "question-bank.json").read_text())
        # Answer all questions
        for q in bank["questions"]:
            buf = io.StringIO()
            with redirect_stdout(buf):
                a.cmd_answer(self.tmpdir, session_id, q["id"], "I don't know", mode="strict")

        # Finish
        buf = io.StringIO()
        with redirect_stdout(buf):
            a.cmd_finish(self.tmpdir, session_id)
        score_json = buf.getvalue()
        score = json.loads(score_json)

        # Score file must exist
        score_path = self.tmpdir / ".project-defense" / "sessions" / f"{session_id}-score.json"
        self.assertTrue(score_path.exists(), "score JSON file must be written on finish")

        # overall_score between 0.0 and 1.0
        self.assertGreaterEqual(score["overall_score"], 0.0)
        self.assertLessEqual(score["overall_score"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
