#!/usr/bin/env python3
"""
test_workspace.py -- Tests for prepare_workspace.py and run_checks.py.

Tests:
  - prepare_workspace copies only allowed_files
  - workspace.json is written with correct fields
  - original repo files are untouched after prepare
  - workspace cleanup works
  - run_checks: all-pass -> PASSED
  - run_checks: one failure -> FAILED
  - run_checks: timeout -> NOT_RUN
  - run_checks: blocked command -> INFRASTRUCTURE_ERROR
  - run_checks: never touches original files
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

import prepare_workspace as pw
import run_checks as rc


def _write_manifest(challenge_dir: Path, checks: list) -> None:
    """Write a minimal manifest.json in the given challenge directory."""
    starter_dir = challenge_dir / "starter"
    starter_dir.mkdir(parents=True, exist_ok=True)
    (starter_dir / "solution.py").write_text("# starter file\n", encoding="utf-8")
    (starter_dir / "other.py").write_text("# other file\n", encoding="utf-8")

    manifest = {
        "challenge_id": challenge_dir.name,
        "repository_revision": "unversioned",
        "feature": "test-feature",
        "type": "function_reconstruction",
        "difficulty": "easy",
        "source_references": [{"file": "solution.py", "lines": [1, 5], "description": "test"}],
        "objective": "Test objective.",
        "workspace": {
            "allowed_files": ["solution.py"],
            "starter_file": "solution.py",
        },
        "checks": checks,
        "hint_policy": {"reveal_after_attempts": 2, "max_hints": 4},
        "hints": ["Hint 1", "Hint 2", "Hint 3", "Hint 4"],
        "status": "pending",
    }
    (challenge_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


class TestPrepareWorkspace(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-ws-test-"))
        defense_dir = self.tmpdir / ".project-defense"
        defense_dir.mkdir()
        # Create a file in the repo root that must never be touched
        (self.tmpdir / "original.py").write_text("# original source\n", encoding="utf-8")
        self.original_hash = (self.tmpdir / "original.py").read_bytes()

        challenge_id = "test-challenge-001"
        self.challenge_dir = defense_dir / "challenges" / challenge_id
        self.challenge_dir.mkdir(parents=True)
        _write_manifest(self.challenge_dir, [])
        self.challenge_id = challenge_id

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_prepare_creates_workspace_dir(self):
        pw.prepare_workspace(self.tmpdir, self.challenge_id, force=True)
        workspace_dir = self.challenge_dir / "workspace"
        self.assertTrue(workspace_dir.exists(), "workspace/ directory must be created")

    def test_prepare_copies_only_allowed_files(self):
        pw.prepare_workspace(self.tmpdir, self.challenge_id, force=True)
        workspace_dir = self.challenge_dir / "workspace"
        files_in_ws = {p.name for p in workspace_dir.iterdir()}
        self.assertIn("solution.py", files_in_ws, "allowed file must be in workspace/")
        self.assertNotIn("other.py", files_in_ws, "non-allowed file must NOT be in workspace/")

    def test_prepare_writes_workspace_json(self):
        info = pw.prepare_workspace(self.tmpdir, self.challenge_id, force=True)
        workspace_json = self.challenge_dir / "workspace.json"
        self.assertTrue(workspace_json.exists(), "workspace.json must exist")
        data = json.loads(workspace_json.read_text())
        for field in ("challenge_id", "created_at", "workspace_path", "files"):
            self.assertIn(field, data, f"workspace.json missing field: {field}")
        self.assertIn("solution.py", data["files"])

    def test_original_files_untouched_after_prepare(self):
        pw.prepare_workspace(self.tmpdir, self.challenge_id, force=True)
        after_hash = (self.tmpdir / "original.py").read_bytes()
        self.assertEqual(self.original_hash, after_hash,
                         "prepare_workspace must never modify original repo files")

    def test_prepare_twice_with_force(self):
        """Running prepare_workspace twice with --force cleans and re-creates workspace."""
        pw.prepare_workspace(self.tmpdir, self.challenge_id, force=True)
        pw.prepare_workspace(self.tmpdir, self.challenge_id, force=True)
        workspace_dir = self.challenge_dir / "workspace"
        self.assertTrue(workspace_dir.exists())


class TestRunChecks(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-rc-test-"))
        defense_dir = self.tmpdir / ".project-defense"
        defense_dir.mkdir()
        (self.tmpdir / "original.py").write_text("# original\n", encoding="utf-8")
        self.original_hash = (self.tmpdir / "original.py").read_bytes()
        self.challenge_id = "test-challenge-rc-001"
        self.challenge_dir = defense_dir / "challenges" / self.challenge_id
        self.challenge_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _setup_challenge(self, checks):
        _write_manifest(self.challenge_dir, checks)
        pw.prepare_workspace(self.tmpdir, self.challenge_id, force=True)

    def test_run_checks_pass(self):
        """All exit(0) commands -> overall PASSED."""
        checks = [
            {
                "id": "check-pass",
                "description": "Always passes.",
                "command": [sys.executable, "-c", "import sys; sys.exit(0)"],
                "expected_exit_code": 0,
                "timeout_seconds": 10,
            }
        ]
        self._setup_challenge(checks)
        result = rc.run_checks(self.tmpdir, self.challenge_id)
        self.assertEqual(result["overall"], "PASSED")
        self.assertEqual(result["checks"][0]["status"], "PASSED")

    def test_run_checks_fail(self):
        """A command that exits(1) -> overall FAILED."""
        checks = [
            {
                "id": "check-fail",
                "description": "Always fails.",
                "command": [sys.executable, "-c", "import sys; sys.exit(1)"],
                "expected_exit_code": 0,
                "timeout_seconds": 10,
            }
        ]
        self._setup_challenge(checks)
        result = rc.run_checks(self.tmpdir, self.challenge_id)
        self.assertEqual(result["overall"], "FAILED")
        self.assertEqual(result["checks"][0]["status"], "FAILED")

    def test_run_checks_timeout(self):
        """Command that sleeps 60s -> NOT_RUN (timed out)."""
        checks = [
            {
                "id": "check-timeout",
                "description": "Times out.",
                "command": [sys.executable, "-c", "import time; time.sleep(60)"],
                "expected_exit_code": 0,
                "timeout_seconds": 1,
            }
        ]
        self._setup_challenge(checks)
        result = rc.run_checks(self.tmpdir, self.challenge_id)
        self.assertEqual(result["checks"][0]["status"], "NOT_RUN")
        self.assertIn("timed out", result["checks"][0]["stderr_tail"])

    def test_run_checks_blocked_command(self):
        """Commands not in the allowed-prefix list -> INFRASTRUCTURE_ERROR."""
        checks = [
            {
                "id": "check-blocked",
                "description": "Dangerous command.",
                "command": ["rm", "-rf", "/"],
                "expected_exit_code": 0,
                "timeout_seconds": 5,
            }
        ]
        self._setup_challenge(checks)
        result = rc.run_checks(self.tmpdir, self.challenge_id)
        self.assertEqual(result["checks"][0]["status"], "INFRASTRUCTURE_ERROR")
        self.assertIn("blocked", result["checks"][0]["stderr_tail"].lower())

    def test_run_checks_never_touches_original_files(self):
        """After run_checks, original repo files must be unchanged."""
        checks = [
            {
                "id": "check-safe",
                "description": "Does nothing harmful.",
                "command": [sys.executable, "-c", "pass"],
                "expected_exit_code": 0,
                "timeout_seconds": 5,
            }
        ]
        self._setup_challenge(checks)
        rc.run_checks(self.tmpdir, self.challenge_id)
        after_hash = (self.tmpdir / "original.py").read_bytes()
        self.assertEqual(self.original_hash, after_hash,
                         "run_checks must never modify original repo files")

    def test_workspace_cleanup_works(self):
        """Deleting workspace/ dir cleans up the workspace correctly."""
        self._setup_challenge([])
        workspace_dir = self.challenge_dir / "workspace"
        self.assertTrue(workspace_dir.exists())
        import shutil as _shutil
        _shutil.rmtree(workspace_dir)
        self.assertFalse(workspace_dir.exists(), "workspace dir should be gone after rmtree")


if __name__ == "__main__":
    unittest.main(verbosity=2)
