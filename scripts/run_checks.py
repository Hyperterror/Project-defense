#!/usr/bin/env python3
"""
run_checks.py -- Run manifest checks against a challenge workspace.

CLI:
  python3 run_checks.py <repo_path> --challenge <challenge-id>

Reads the manifest.checks list, runs each command in the workspace directory
with a 30-second timeout, and writes result.json.

Security: only commands whose first token is in the ALLOWED_PREFIXES list are
executed. All others are recorded as INFRASTRUCTURE_ERROR.

NEVER runs commands outside the workspace directory.
Stdlib only, Python 3.8+.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# Allowed command prefixes (first element of the command list).
# Matching is done against the executable basename (handles full paths like
# sys.executable, and strips a trailing .exe on Windows).
ALLOWED_PREFIXES = {"python3", "python", "node", "npm", "pytest", "unittest"}


def _is_allowed(command: list) -> bool:
    """Return True if the command's first token (by basename) is in the allow-list."""
    if not command:
        return False
    first = command[0]
    # Handle string-style compound commands like "npm test" (split on whitespace)
    if " " in first:
        first = first.split()[0]
    # Reduce to basename so full paths (sys.executable) still match "python"
    base = os.path.basename(first)
    # Strip a trailing .exe (Windows) for matching
    if base.lower().endswith(".exe"):
        base = base[:-4]
    return base in ALLOWED_PREFIXES


def run_checks(repo_root: Path, challenge_id: str) -> dict:
    """Run all checks from the manifest and return the result dict."""
    defense_dir = repo_root / ".project-defense"
    challenge_dir = defense_dir / "challenges" / challenge_id
    manifest_path = challenge_dir / "manifest.json"
    workspace_dir = challenge_dir / "workspace"

    if not manifest_path.exists():
        sys.exit(
            f"Error: manifest not found at '{manifest_path}'. "
            "Run generate_challenge.py first."
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"Error: '{manifest_path}' contains invalid JSON.\nDetails: {exc}")

    if not workspace_dir.exists():
        sys.exit(
            f"Error: workspace directory '{workspace_dir}' does not exist. "
            "Run prepare_workspace.py first."
        )

    checks = manifest.get("checks", [])
    check_results = []
    overall = "PASSED"

    for check in checks:
        check_id = check.get("id", "unknown")
        command = check.get("command", [])
        timeout = min(check.get("timeout_seconds", 30), 30)

        result_entry = {
            "id": check_id,
            "status": "NOT_RUN",
            "exit_code": None,
            "stderr_tail": "",
            "duration_seconds": 0.0,
        }

        # Security check: block disallowed commands
        if not _is_allowed(command):
            result_entry["status"] = "INFRASTRUCTURE_ERROR"
            result_entry["stderr_tail"] = (
                f"Command blocked by security policy. "
                f"Allowed prefixes: {sorted(ALLOWED_PREFIXES)}. "
                f"Got: {command[0] if command else '(empty)'}"
            )
            check_results.append(result_entry)
            overall = "INFRASTRUCTURE_ERROR"
            continue

        start = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                cwd=str(workspace_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration = time.monotonic() - start
            result_entry["duration_seconds"] = round(duration, 3)
            result_entry["exit_code"] = proc.returncode
            result_entry["stderr_tail"] = proc.stderr[-200:] if proc.stderr else ""

            if proc.returncode == 0:
                result_entry["status"] = "PASSED"
            else:
                result_entry["status"] = "FAILED"
                if overall == "PASSED":
                    overall = "FAILED"

        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            result_entry["status"] = "NOT_RUN"
            result_entry["stderr_tail"] = f"timed out after {timeout}s"
            result_entry["duration_seconds"] = round(duration, 3)
            if overall == "PASSED":
                overall = "FAILED"

        except FileNotFoundError as exc:
            result_entry["status"] = "INFRASTRUCTURE_ERROR"
            result_entry["stderr_tail"] = f"command not found: {exc}"
            overall = "INFRASTRUCTURE_ERROR"

        except Exception as exc:
            result_entry["status"] = "INFRASTRUCTURE_ERROR"
            result_entry["stderr_tail"] = str(exc)[:200]
            overall = "INFRASTRUCTURE_ERROR"

        check_results.append(result_entry)

    # Overall is PASSED only if every check passed
    all_passed = all(r["status"] == "PASSED" for r in check_results)
    if check_results and all_passed:
        overall = "PASSED"
    elif not check_results:
        overall = "PASSED"

    result = {
        "challenge_id": challenge_id,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "checks": check_results,
        "overall": overall,
    }

    result_path = challenge_dir / "result.json"
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Run manifest checks against a challenge workspace."
    )
    parser.add_argument("repo_path", help="Path to the repository root.")
    parser.add_argument("--challenge", required=True, metavar="CHALLENGE_ID",
                        help="The challenge ID.")
    args = parser.parse_args()

    repo_root = Path(args.repo_path).resolve()
    if not repo_root.exists():
        sys.exit(f"Error: repository path '{repo_root}' does not exist.")

    result = run_checks(repo_root, args.challenge)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
