#!/usr/bin/env python3
"""
save_corrections.py -- Reads and writes .project-defense/corrections.json.

The file is a JSON object keyed by stable entry ID (string).
Each value: { "decision": "confirmed"|"corrected"|"unknown", "note": str|null, "timestamp": str }

CLI:
  save_corrections.py <repo-root> --list
      Prints all entries as a table.
  save_corrections.py <repo-root> --set <id> <decision> [--note <text>]
      Writes one entry. Decision must be confirmed, corrected, or unknown.
  save_corrections.py <repo-root> --get <id>
      Prints one entry as JSON.

Stdlib only, Python 3.8+.
"""

import argparse
import json
import sys
import tempfile
import os
from datetime import datetime, timezone
from pathlib import Path


VALID_DECISIONS = {"confirmed", "corrected", "unknown"}


# -----------------------------------------------------------------------
# Core functions (importable by other scripts)
# -----------------------------------------------------------------------


def load_corrections(path: Path) -> dict:
    """Load corrections.json; return {} if file does not exist.
    Raises SystemExit with an actionable message if the file is corrupt.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(
            f"Error: {path} contains invalid JSON and cannot be loaded safely. "
            f"Fix or delete the file before proceeding.\nDetails: {exc}"
        )
    if not isinstance(data, dict):
        sys.exit(
            f"Error: {path} must be a JSON object (dict), got {type(data).__name__}. "
            "Fix or delete the file before proceeding."
        )
    return data


def save_corrections(path: Path, corrections: dict) -> None:
    """Write corrections dict to path atomically (temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Validate before writing
    for entry_id, entry in corrections.items():
        if not isinstance(entry, dict):
            sys.exit(f"Error: entry '{entry_id}' must be a dict, got {type(entry).__name__}.")
        if entry.get("decision") not in VALID_DECISIONS:
            sys.exit(
                f"Error: entry '{entry_id}' has invalid decision '{entry.get('decision')}'. "
                f"Must be one of: {', '.join(sorted(VALID_DECISIONS))}."
            )
    # Write atomically
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".corrections-tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(corrections, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def update_entry(corrections: dict, entry_id: str, decision: str, note: str = None) -> dict:
    """Create or update a single entry in the corrections dict.
    Returns the updated dict (mutates in place and returns it).
    Raises ValueError if decision is invalid.
    """
    if decision not in VALID_DECISIONS:
        raise ValueError(
            f"Invalid decision '{decision}'. Must be one of: {', '.join(sorted(VALID_DECISIONS))}."
        )
    corrections[entry_id] = {
        "decision": decision,
        "note": note,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return corrections


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Manage .project-defense/corrections.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("repo_root", help="Path to the repository root")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="Print all entries as a table")
    group.add_argument("--set", nargs=2, metavar=("ID", "DECISION"),
                       help="Set an entry. DECISION must be confirmed, corrected, or unknown.")
    group.add_argument("--get", metavar="ID", help="Print one entry as JSON")
    parser.add_argument("--note", default=None, help="Optional note text for --set")

    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists():
        sys.exit(f"Error: repository root '{repo_root}' does not exist.")

    corrections_path = repo_root / ".project-defense" / "corrections.json"
    corrections = load_corrections(corrections_path)

    if args.list:
        if not corrections:
            print("No corrections recorded.")
            return
        print(f"{'ID':<30} {'DECISION':<12} {'NOTE':<40} TIMESTAMP")
        print("-" * 100)
        for entry_id, entry in sorted(corrections.items()):
            note = (entry.get("note") or "")[:38]
            print(f"{entry_id:<30} {entry.get('decision', ''):<12} {note:<40} {entry.get('timestamp', '')}")

    elif args.set:
        entry_id, decision = args.set
        if decision not in VALID_DECISIONS:
            sys.exit(
                f"Error: decision must be one of {', '.join(sorted(VALID_DECISIONS))}. Got: '{decision}'."
            )
        update_entry(corrections, entry_id, decision, args.note)
        save_corrections(corrections_path, corrections)
        print(f"Saved correction for '{entry_id}': {decision}")

    elif args.get:
        entry = corrections.get(args.get)
        if entry is None:
            sys.exit(f"Error: no entry found for ID '{args.get}'.")
        print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
