#!/usr/bin/env python3
"""
save_progress.py -- Manage assessment session files in .project-defense/sessions/.

Session JSON structure:
  {
    "session_id": "sess-<8-char-sha256>",
    "session_identity": "<sha256 from project-graph.json>",
    "created_at": "ISO-8601",
    "updated_at": "ISO-8601",
    "mode": "assessment"|"interview"|"practice",
    "status": "active"|"completed"|"abandoned",
    "questions": [
      {
        "question_id": str,
        "rubric_id": str,
        "answer": str|null,
        "scores": { "<concept>": 0-3 },
        "category": str
      }
    ],
    "coding_results": [],
    "summary": null | { ... }
  }

CLI:
  save_progress.py <repo-root> new --mode <mode>
      Creates a new session, prints session_id.
  save_progress.py <repo-root> update <session-id> --answer <q-id> <answer-text>
      Appends or updates an answer.
  save_progress.py <repo-root> update <session-id> --score <q-id> <concept> <0-3>
      Records a concept score.
  save_progress.py <repo-root> complete <session-id>
      Sets status to "completed".
  save_progress.py <repo-root> list
      Prints session IDs and statuses for the current session_identity.

Stdlib only, Python 3.8+.
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


VALID_MODES = {"assessment", "interview", "practice"}
VALID_STATUSES = {"active", "completed", "abandoned"}


# -----------------------------------------------------------------------
# Core functions (importable by other scripts)
# -----------------------------------------------------------------------


def _get_session_identity(repo_root: Path) -> str:
    """Read session_identity from project-graph.json, or '' if not available."""
    graph_path = repo_root / ".project-defense" / "project-graph.json"
    if not graph_path.exists():
        return ""
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        return graph.get("session_identity", "")
    except Exception:
        return ""


def _sessions_dir(repo_root: Path) -> Path:
    d = repo_root / ".project-defense" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _session_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.json"


def _write_session(path: Path, session: dict) -> None:
    """Write session atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".sess-tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def create_session(sessions_dir: Path, session_id: str, session_identity: str, mode: str) -> dict:
    """Create a new session dict and write it to sessions_dir.

    Returns the session dict.
    """
    if mode not in VALID_MODES:
        sys.exit(f"Error: invalid mode '{mode}'. Must be one of: {', '.join(sorted(VALID_MODES))}.")
    now = datetime.now(timezone.utc).isoformat()
    session = {
        "session_id": session_id,
        "session_identity": session_identity,
        "created_at": now,
        "updated_at": now,
        "mode": mode,
        "status": "active",
        "questions": [],
        "coding_results": [],
        "summary": None,
    }
    path = _session_path(sessions_dir, session_id)
    _write_session(path, session)
    return session


def load_session(sessions_dir: Path, session_id: str) -> dict:
    """Load and return a session dict.  Raises SystemExit if not found or corrupt."""
    path = _session_path(sessions_dir, session_id)
    if not path.exists():
        sys.exit(f"Error: session '{session_id}' not found in '{sessions_dir}'.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"Error: session file '{path}' contains invalid JSON.\nDetails: {exc}")


def update_session(sessions_dir: Path, session_id: str, updates: dict) -> dict:
    """Apply updates dict to session and persist.  Returns updated session."""
    session = load_session(sessions_dir, session_id)
    session.update(updates)
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = _session_path(sessions_dir, session_id)
    _write_session(path, session)
    return session


def list_sessions(sessions_dir: Path, session_identity: str = None) -> list:
    """Return list of session dicts from sessions_dir.

    If session_identity is given, only return sessions matching that identity.
    """
    result = []
    if not sessions_dir.exists():
        return result
    for p in sorted(sessions_dir.glob("sess-*.json")):
        try:
            s = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if session_identity is not None and s.get("session_identity") != session_identity:
            continue
        result.append(s)
    return result


def _make_session_id(session_identity: str, created_at: str) -> str:
    raw = session_identity + created_at
    return "sess-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Manage .project-defense/sessions/ files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("repo_root", help="Path to the repository root.")
    sub = parser.add_subparsers(dest="command", required=True)

    # new
    new_p = sub.add_parser("new", help="Create a new session.")
    new_p.add_argument("--mode", required=True, choices=list(VALID_MODES),
                       help="Session mode.")

    # update
    upd_p = sub.add_parser("update", help="Update an existing session.")
    upd_p.add_argument("session_id", help="Session ID.")
    upd_group = upd_p.add_mutually_exclusive_group(required=True)
    upd_group.add_argument("--answer", nargs=2, metavar=("Q_ID", "ANSWER"),
                           help="Record an answer for a question.")
    upd_group.add_argument("--score", nargs=3, metavar=("Q_ID", "CONCEPT", "SCORE"),
                           help="Record a concept score (0-3) for a question.")

    # complete
    cmp_p = sub.add_parser("complete", help="Mark session as completed.")
    cmp_p.add_argument("session_id", help="Session ID.")

    # list
    sub.add_parser("list", help="List sessions for current repo identity.")

    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists():
        sys.exit(f"Error: repository root '{repo_root}' does not exist.")

    sessions_dir = _sessions_dir(repo_root)
    session_identity = _get_session_identity(repo_root)

    if args.command == "new":
        now = datetime.now(timezone.utc).isoformat()
        session_id = _make_session_id(session_identity, now)
        session = create_session(sessions_dir, session_id, session_identity, args.mode)
        print(session_id)

    elif args.command == "update":
        session = load_session(sessions_dir, args.session_id)
        questions = session.get("questions", [])

        if args.answer:
            q_id, answer_text = args.answer
            # Find or create question entry
            q_entry = next((q for q in questions if q["question_id"] == q_id), None)
            if q_entry is None:
                q_entry = {
                    "question_id": q_id,
                    "rubric_id": "",
                    "answer": answer_text,
                    "scores": {},
                    "category": "",
                }
                questions.append(q_entry)
            else:
                q_entry["answer"] = answer_text
            session["questions"] = questions
            update_session(sessions_dir, args.session_id, {"questions": questions})
            print(f"Answer recorded for question '{q_id}'.")

        elif args.score:
            q_id, concept, score_str = args.score
            try:
                score_val = int(score_str)
                if not 0 <= score_val <= 3:
                    raise ValueError
            except ValueError:
                sys.exit(f"Error: score must be an integer 0-3. Got: '{score_str}'.")
            q_entry = next((q for q in questions if q["question_id"] == q_id), None)
            if q_entry is None:
                q_entry = {
                    "question_id": q_id,
                    "rubric_id": "",
                    "answer": None,
                    "scores": {},
                    "category": "",
                }
                questions.append(q_entry)
            q_entry.setdefault("scores", {})[concept] = score_val
            session["questions"] = questions
            update_session(sessions_dir, args.session_id, {"questions": questions})
            print(f"Score {score_val} recorded for concept '{concept}' in question '{q_id}'.")

    elif args.command == "complete":
        update_session(sessions_dir, args.session_id, {"status": "completed"})
        print(f"Session '{args.session_id}' marked as completed.")

    elif args.command == "list":
        sessions = list_sessions(sessions_dir, session_identity or None)
        if not sessions:
            print("No sessions found for this repository.")
            return
        print(f"{'SESSION ID':<20} {'MODE':<12} {'STATUS':<12} CREATED")
        print("-" * 70)
        for s in sessions:
            print(f"{s.get('session_id', ''):<20} {s.get('mode', ''):<12} {s.get('status', ''):<12} {s.get('created_at', '')}")


if __name__ == "__main__":
    main()
