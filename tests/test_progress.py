#!/usr/bin/env python3
"""
test_progress.py -- Tests for scripts/save_progress.py.

Tests:
  - create/load/update session roundtrip
  - list_sessions returns only sessions matching session_identity
  - concurrent writes do not corrupt data (use temp dirs)
  - missing session raises clear error
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

import save_progress as sp


class TestProgress(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-progress-test-"))
        defense_dir = self.tmpdir / ".project-defense"
        defense_dir.mkdir()
        (defense_dir / "project-graph.json").write_text(
            json.dumps({"session_identity": "identity-A", "project": {}, "frontend": {},
                       "backend": {}, "data": {}, "auth": {}, "user_flows": [],
                       "data_flows": [], "risks": [], "uncertainties": []}),
            encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_load_update_roundtrip(self):
        sessions_dir = sp._sessions_dir(self.tmpdir)
        identity = sp._get_session_identity(self.tmpdir)
        now = "2024-01-01T00:00:00+00:00"
        session_id = sp._make_session_id(identity, now)
        # Create
        sp.create_session(sessions_dir, session_id, identity, "assessment")
        # Load
        loaded = sp.load_session(sessions_dir, session_id)
        self.assertEqual(loaded["session_id"], session_id)
        self.assertEqual(loaded["session_identity"], identity)
        # Update
        sp.update_session(sessions_dir, session_id, {"status": "completed"})
        loaded2 = sp.load_session(sessions_dir, session_id)
        self.assertEqual(loaded2["status"], "completed")

    def test_list_sessions_by_identity(self):
        sessions_dir = sp._sessions_dir(self.tmpdir)
        identity_a = "identity-A"
        now1 = "2024-01-01T00:00:00+00:00"
        now2 = "2024-01-01T00:00:01+00:00"
        sid1 = sp._make_session_id(identity_a, now1)
        sid2 = sp._make_session_id(identity_a, now2)
        sp.create_session(sessions_dir, sid1, identity_a, "assessment")
        sp.create_session(sessions_dir, sid2, identity_a, "interview")
        # Create a session with a different identity
        identity_b = "identity-B"
        now3 = "2024-01-01T00:00:02+00:00"
        sid3 = sp._make_session_id(identity_b, now3)
        sp.create_session(sessions_dir, sid3, identity_b, "assessment")

        # List all
        all_sessions = sp.list_sessions(sessions_dir)
        self.assertEqual(len(all_sessions), 3, "list_sessions should return all sessions")

        # List by identity A
        matching = sp.list_sessions(sessions_dir, session_identity=identity_a)
        self.assertEqual(len(matching), 2, "Should return only the two identity-A sessions")
        for s in matching:
            self.assertEqual(s["session_identity"], identity_a)

    def test_concurrent_writes_no_corruption(self):
        """Simulate concurrent writes to the same session file.

        The atomic write (temp file + rename) must ensure no corruption. We
        do sequential writes here and confirm each round leaves the file valid.
        """
        sessions_dir = sp._sessions_dir(self.tmpdir)
        identity = sp._get_session_identity(self.tmpdir)
        now = "2024-01-01T00:00:00+00:00"
        session_id = sp._make_session_id(identity, now)
        sp.create_session(sessions_dir, session_id, identity, "assessment")

        # Write many times and verify each write leaves a valid file
        for i in range(10):
            sp.update_session(sessions_dir, session_id, {"status": "active"})
            loaded = sp.load_session(sessions_dir, session_id)
            # File must always be valid JSON
            self.assertEqual(loaded["session_id"], session_id)
            self.assertEqual(loaded["status"], "active")

    def test_missing_session_raises_clear_error(self):
        """Loading a non-existent session should exit with a clear message."""
        sessions_dir = sp._sessions_dir(self.tmpdir)
        with self.assertRaises(SystemExit):
            sp.load_session(sessions_dir, "sess-doesnotexist")

    def test_atomic_write_preserves_on_failure(self):
        """If os.replace fails, the original file should remain intact."""
        sessions_dir = sp._sessions_dir(self.tmpdir)
        identity = sp._get_session_identity(self.tmpdir)
        now = "2024-01-01T00:00:00+00:00"
        session_id = sp._make_session_id(identity, now)
        sp.create_session(sessions_dir, session_id, identity, "assessment")
        original = sp.load_session(sessions_dir, session_id)
        original_status = original["status"]

        # Monkey-patch os.replace to raise, then attempt an update
        import os
        orig_replace = os.replace
        os.replace = lambda *a, **kw: (_ for _ in ()).throw(OSError("simulated"))
        try:
            with self.assertRaises(OSError):
                sp.update_session(sessions_dir, session_id, {"status": "completed"})
        finally:
            os.replace = orig_replace

        # Original file must still be valid
        loaded = sp.load_session(sessions_dir, session_id)
        self.assertEqual(loaded["status"], original_status, "Failed write must not corrupt existing file")

    def test_rubric_concepts_lists_the_real_names(self):
        """A known rubric resolves to its concepts; an unknown id resolves to none."""
        self.assertIn(
            "password-verification",
            sp.rubric_concepts("explanation-auth-v1"),
        )
        self.assertEqual(sp.rubric_concepts("does-not-exist"), [])
        self.assertEqual(sp.rubric_concepts(""), [])


class TestScoreCli(unittest.TestCase):
    """The --score command must refuse concept names the rubric does not define."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-score-cli-"))
        defense_dir = self.tmpdir / ".project-defense"
        defense_dir.mkdir()
        (defense_dir / "project-graph.json").write_text(
            json.dumps({"session_identity": "identity-A"}),
            encoding="utf-8",
        )
        sessions_dir = sp._sessions_dir(self.tmpdir)
        self.session_id = sp._make_session_id("identity-A", "2024-01-01T00:00:00+00:00")
        session = sp.create_session(sessions_dir, self.session_id, "identity-A", "assessment")
        session["questions"] = [{
            "question_id": "q-e002",
            "rubric_id": "explanation-auth-v1",
            "answer": "some answer",
            "scores": {"request-lifecycle": 1, "credential-issuance": 1},
            "scored_by": "heuristic",
        }]
        sp.update_session(sessions_dir, self.session_id, {"questions": session["questions"]})

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, *args):
        import subprocess
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "save_progress.py"), str(self.tmpdir)]
            + list(args),
            capture_output=True, text=True,
        )

    def _question(self):
        session = sp.load_session(sp._sessions_dir(self.tmpdir), self.session_id)
        return next(q for q in session["questions"] if q["question_id"] == "q-e002")

    def test_unknown_concept_exits_with_the_valid_names(self):
        result = self._run("update", self.session_id, "--score", "q-e002", "trade-off reasoning", "3")
        self.assertNotEqual(result.returncode, 0, "A concept the rubric does not define must be refused")
        self.assertIn("password-verification", result.stderr + result.stdout,
                      "The error must list the concepts that are valid")
        self.assertEqual(self._question()["scores"].get("trade-off reasoning"), None,
                         "A refused score must not be written")

    def test_agent_score_replaces_heuristic_values(self):
        result = self._run("update", self.session_id, "--score", "q-e002", "password-verification", "3")
        self.assertEqual(result.returncode, 0, result.stderr)
        question = self._question()
        self.assertEqual(question["scored_by"], "agent")
        self.assertEqual(
            question["scores"], {"password-verification": 3},
            "Recording a rubric score must clear the keyword fallback values, "
            "which measured a different thing",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
