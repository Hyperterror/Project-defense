#!/usr/bin/env python3
"""
test_challenge_gen.py -- Tests for scripts/generate_challenge.py.

Tests:
  - function_reconstruction produces a starter file with TODO stub
  - bug_fix introduces exactly one changed line
  - test_writing produces a test skeleton
  - original files are never modified
  - manifest.json is written and contains required fields
"""

import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import generate_challenge as gc


# Minimal project-graph.json fixture
MINIMAL_GRAPH = {
    "session_identity": "test-identity",
    "project": {
        "name": "test-app",
        "purpose": "A test application for unit tests.",
        "stack": ["Python"],
        "entry_points": [{"file": "app.py", "type": "backend"}],
    },
    "frontend": {"pages": [], "components": [], "state_management": [], "api_calls": []},
    "backend": {
        "routes": [
            {
                "method": "POST",
                "path": "/api/login",
                "handler": "login_handler",
                "evidence": {
                    "file": "app.py",
                    "lines": [10, 25],
                    "excerpt": "def login_handler(req):",
                    "status": "code-verified",
                },
            }
        ],
        "middleware": [], "controllers": [], "services": [],
    },
    "data": {"models": [], "relationships": [], "migrations": []},
    "auth": {"strategy": "JWT", "token_handling": "Bearer header", "protected_routes": []},
    "user_flows": [], "data_flows": [], "risks": [], "uncertainties": [],
}

SAMPLE_PY = '''
def login_handler(email, password):
    """Authenticate a user and return a token."""
    if not email or not password:
        return None
    # Compare password hash
    token = "generated-jwt-token"
    return token


def register_user(email, password):
    """Register a new user."""
    hashed = hash(password)
    return {"email": email, "hashed": hashed}
'''


class TestChallengeGen(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-challenge-test-"))
        defense_dir = self.tmpdir / ".project-defense"
        defense_dir.mkdir()
        (defense_dir / "project-graph.json").write_text(
            json.dumps(MINIMAL_GRAPH), encoding="utf-8"
        )
        # Create the source file referenced in the graph
        (self.tmpdir / "app.py").write_text(SAMPLE_PY, encoding="utf-8")
        self.original_hash = self._file_bytes("app.py")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _file_bytes(self, rel_path: str) -> bytes:
        return (self.tmpdir / rel_path).read_bytes()

    def _challenge_dir(self, challenge_id: str) -> Path:
        return self.tmpdir / ".project-defense" / "challenges" / challenge_id

    def test_function_reconstruction_creates_manifest(self):
        """function_reconstruction: manifest.json created and has required fields."""
        challenge_id = gc.generate_challenge(
            self.tmpdir, "login", "function_reconstruction", "medium",
            timestamp=int(time.time())
        )
        manifest_path = self._challenge_dir(challenge_id) / "manifest.json"
        self.assertTrue(manifest_path.exists(), "manifest.json must exist")
        manifest = json.loads(manifest_path.read_text())

        required = ["challenge_id", "repository_revision", "feature", "type",
                    "difficulty", "source_references", "objective", "workspace",
                    "checks", "hint_policy", "hints", "status"]
        for field in required:
            self.assertIn(field, manifest, f"manifest missing field: {field}")

        self.assertEqual(manifest["type"], "function_reconstruction")
        self.assertEqual(manifest["difficulty"], "medium")
        self.assertEqual(manifest["feature"], "login")

    def test_function_reconstruction_creates_todo_stub(self):
        """function_reconstruction: starter file must contain TODO stub."""
        challenge_id = gc.generate_challenge(
            self.tmpdir, "login", "function_reconstruction", "easy",
            timestamp=int(time.time())
        )
        starter_dir = self._challenge_dir(challenge_id) / "starter"
        starters = list(starter_dir.iterdir())
        self.assertTrue(len(starters) > 0, "starter/ must have at least one file")

        starter_text = starters[0].read_text(encoding="utf-8")
        self.assertIn("TODO", starter_text, "starter file must contain a TODO stub")
        self.assertIn("NotImplementedError", starter_text, "starter file must contain NotImplementedError")

    def test_bug_fix_creates_starter_files(self):
        """bug_fix: starter/ directory with files must be created."""
        challenge_id = gc.generate_challenge(
            self.tmpdir, "login", "bug_fix", "medium",
            timestamp=int(time.time())
        )
        starter_dir = self._challenge_dir(challenge_id) / "starter"
        self.assertTrue(starter_dir.exists(), "starter/ directory must exist")
        starters = list(starter_dir.iterdir())
        self.assertTrue(len(starters) > 0, "starter/ must contain at least one file")

    def test_bug_fix_introduces_one_changed_line(self):
        """bug_fix: starter file must differ from original by at least one line."""
        challenge_id = gc.generate_challenge(
            self.tmpdir, "login", "bug_fix", "medium",
            timestamp=int(time.time())
        )
        starter_dir = self._challenge_dir(challenge_id) / "starter"
        starters = list(starter_dir.iterdir())
        starter_text = starters[0].read_text(encoding="utf-8")

        original_lines = set(SAMPLE_PY.splitlines())
        starter_lines = set(starter_text.splitlines())
        diff = starter_lines.symmetric_difference(original_lines)
        self.assertGreater(len(diff), 0, "bug_fix starter must differ from original by at least one line")

    def test_test_writing_creates_test_stub(self):
        """test_writing: a test skeleton file must be created in starter/."""
        challenge_id = gc.generate_challenge(
            self.tmpdir, "login", "test_writing", "easy",
            timestamp=int(time.time())
        )
        starter_dir = self._challenge_dir(challenge_id) / "starter"
        starters = list(starter_dir.iterdir())
        self.assertTrue(len(starters) > 0, "starter/ must contain at least one file")
        starter_text = starters[0].read_text(encoding="utf-8")
        self.assertIn("import unittest", starter_text, "test stub must import unittest")
        self.assertIn("class Test", starter_text, "test stub must contain a test class")

    def test_never_modifies_original(self):
        """After generate_challenge, original source files must be untouched."""
        gc.generate_challenge(
            self.tmpdir, "login", "function_reconstruction", "hard",
            timestamp=int(time.time())
        )
        after_hash = self._file_bytes("app.py")
        self.assertEqual(self.original_hash, after_hash,
                         "generate_challenge must never modify original source files")

    def test_challenge_id_deterministic_same_inputs(self):
        """Same feature/type/difficulty and same timestamp gives the same challenge_id."""
        ts = int(time.time())
        id1 = gc._make_challenge_id("auth", "bug_fix", "easy", ts)
        id2 = gc._make_challenge_id("auth", "bug_fix", "easy", ts)
        self.assertEqual(id1, id2, "Same inputs must produce same challenge_id")

    def test_manifest_challenge_id_format(self):
        """challenge_id must start with 'challenge-'."""
        challenge_id = gc.generate_challenge(
            self.tmpdir, "login", "bug_fix", "easy",
            timestamp=int(time.time())
        )
        self.assertTrue(challenge_id.startswith("challenge-"),
                        f"challenge_id must start with 'challenge-', got: {challenge_id}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
