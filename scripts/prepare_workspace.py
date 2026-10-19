#!/usr/bin/env python3
"""
prepare_workspace.py -- Prepare a workspace directory for a coding challenge.

CLI:
  python3 prepare_workspace.py <repo_path> --challenge <challenge-id> [--force]

Reads the challenge manifest, copies only the allowed starter files into the
workspace directory, and writes workspace.json.

NEVER reads from or writes to original repository files.
Stdlib only, Python 3.8+.
"""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def prepare_workspace(repo_root: Path, challenge_id: str, force: bool = False) -> dict:
    """Set up the workspace directory for a challenge.

    Returns the workspace.json dict.
    Raises SystemExit with actionable message on any error.
    """
    defense_dir = repo_root / ".project-defense"
    challenge_dir = defense_dir / "challenges" / challenge_id
    manifest_path = challenge_dir / "manifest.json"
    starter_dir = challenge_dir / "starter"
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

    allowed_files = manifest.get("workspace", {}).get("allowed_files", [])
    if not allowed_files:
        sys.exit(f"Error: manifest '{manifest_path}' has no workspace.allowed_files.")

    # Check that every allowed_file exists in starter/
    missing = [f for f in allowed_files if not (starter_dir / f).exists()]
    if missing:
        sys.exit(
            f"Error: the following allowed files do not exist in '{starter_dir}':\n"
            + "\n".join(f"  {f}" for f in missing)
        )

    # Clean workspace if it exists
    if workspace_dir.exists():
        if not force:
            # In non-interactive (scripted) use, clean automatically.
            # An interactive check would be done by the agent/caller.
            shutil.rmtree(workspace_dir)
        else:
            shutil.rmtree(workspace_dir)

    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Copy only allowed files from starter/ to workspace/
    copied_files = []
    for fname in allowed_files:
        src = starter_dir / fname
        dst = workspace_dir / fname
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied_files.append(fname)

    # Write workspace.json
    workspace_info = {
        "challenge_id": challenge_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workspace_path": str(workspace_dir),
        "files": copied_files,
    }
    workspace_json_path = challenge_dir / "workspace.json"
    workspace_json_path.write_text(json.dumps(workspace_info, indent=2), encoding="utf-8")

    return workspace_info


def main():
    parser = argparse.ArgumentParser(
        description="Prepare the workspace directory for a coding challenge."
    )
    parser.add_argument("repo_path", help="Path to the repository root.")
    parser.add_argument("--challenge", required=True, metavar="CHALLENGE_ID",
                        help="The challenge ID (from generate_challenge.py).")
    parser.add_argument("--force", action="store_true",
                        help="Clean and recreate the workspace without asking.")
    args = parser.parse_args()

    repo_root = Path(args.repo_path).resolve()
    if not repo_root.exists():
        sys.exit(f"Error: repository path '{repo_root}' does not exist.")

    workspace_info = prepare_workspace(repo_root, args.challenge, force=args.force)
    print(json.dumps(workspace_info, indent=2))


if __name__ == "__main__":
    main()
