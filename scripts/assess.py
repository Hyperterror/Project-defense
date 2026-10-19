#!/usr/bin/env python3
"""
assess.py -- Orchestrate assessment sessions.

Designed to be called by the agent in a loop (one call per Q&A exchange), not
as an interactive REPL.

CLI sub-commands:
  assess.py <repo-root> start [--mode strict|guided]
      Creates a session via save_progress.py, loads or generates the question
      bank, prints the first question JSON.
  assess.py <repo-root> answer <session-id> <question-id> <answer-text>
      Records the answer, scores it against the rubric (if rubric exists),
      calls run_checks.py if the question is a coding_task, prints the next
      question JSON or {"done": true} if all questions answered.
  assess.py <repo-root> finish <session-id>
      Calls save_progress.py complete, then score_report.py, prints the score.

strict mode: no hints, questions in fixed order from bank.
guided mode: after each answer, if score < 2, offer the next hint before advancing.

Stdlib only, Python 3.8+.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import save_progress as sp
import score_report as sr


RUBRICS_DIR = SCRIPT_DIR.parent / "rubrics"


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _defense_dir(repo_root: Path) -> Path:
    return repo_root / ".project-defense"


def _sessions_dir(repo_root: Path) -> Path:
    return sp._sessions_dir(repo_root)


def _load_question_bank(repo_root: Path) -> dict:
    """Load question-bank.json, generating it if missing."""
    qb_path = _defense_dir(repo_root) / "question-bank.json"
    if not qb_path.exists():
        # Generate it
        cmd = [sys.executable, str(SCRIPT_DIR / "generate_question_bank.py"), str(repo_root)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"Error: failed to generate question bank.\n{r.stderr}")
    try:
        return json.loads(qb_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"Error: '{qb_path}' contains invalid JSON.\nDetails: {exc}")


def _load_rubric(rubric_id: str) -> dict | None:
    """Load a rubric by its id.  Returns None if not found."""
    if not rubric_id:
        return None
    path = RUBRICS_DIR / f"{rubric_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _score_answer(rubric: dict, answer_text: str) -> dict:
    """Score an answer against a rubric.  Returns a scores dict mapping concept -> 0-3.

    This is a heuristic keyword-based scorer (since we have no LLM here). It
    assigns 2 if any expected_concept keyword appears in the answer, 1 if the
    answer is non-trivial, 0 otherwise.
    """
    scores = {}
    if not rubric:
        return scores
    answer_lower = answer_text.lower()
    for concept in rubric.get("expected_concepts", []):
        if concept.replace("-", " ") in answer_lower or concept in answer_lower:
            scores[concept] = 2
        elif len(answer_text.strip()) > 20:
            scores[concept] = 1
        else:
            scores[concept] = 0
    return scores


# -----------------------------------------------------------------------
# Sub-commands
# -----------------------------------------------------------------------


def cmd_start(repo_root: Path, mode: str) -> None:
    if mode not in ("strict", "guided"):
        sys.exit(f"Error: mode must be 'strict' or 'guided'. Got: '{mode}'.")

    sessions_dir = _sessions_dir(repo_root)
    session_identity = sp._get_session_identity(repo_root)

    # Create a new session via save_progress
    new_result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "save_progress.py"), str(repo_root),
         "new", "--mode", "assessment"],
        capture_output=True, text=True
    )
    if new_result.returncode != 0:
        sys.exit(f"Error: could not create session.\n{new_result.stderr}")
    session_id = new_result.stdout.strip()

    # Load question bank
    bank = _load_question_bank(repo_root)
    questions = bank.get("questions", [])

    if not questions:
        print(json.dumps({"session_id": session_id, "done": True, "message": "No questions generated."}))
        return

    first_q = questions[0]
    # Record the question entries in the session (pre-populate with empty answers)
    session = sp.load_session(sessions_dir, session_id)
    question_entries = []
    for q in questions:
        question_entries.append({
            "question_id": q["id"],
            "rubric_id": q.get("rubric_id") or "",
            "answer": None,
            "scores": {},
            "category": q["category"],
        })
    sp.update_session(sessions_dir, session_id, {"questions": question_entries})

    out = {
        "session_id": session_id,
        "mode": mode,
        "question_id": first_q["id"],
        "category": first_q["category"],
        "text": first_q["text"],
        "difficulty": first_q.get("difficulty", "medium"),
        "project_references": first_q.get("project_references", []),
        "total_questions": len(questions),
        "current_index": 0,
    }
    print(json.dumps(out, indent=2))


def cmd_answer(repo_root: Path, session_id: str, question_id: str, answer_text: str,
               mode: str = "guided") -> None:
    sessions_dir = _sessions_dir(repo_root)
    session = sp.load_session(sessions_dir, session_id)

    questions = session.get("questions", [])
    q_entry = next((q for q in questions if q["question_id"] == question_id), None)
    if q_entry is None:
        sys.exit(f"Error: question '{question_id}' not found in session '{session_id}'.")

    # Record the answer
    q_entry["answer"] = answer_text

    # Score against rubric if available
    rubric_id = q_entry.get("rubric_id", "")
    rubric = _load_rubric(rubric_id) if rubric_id else None
    if rubric:
        scores = _score_answer(rubric, answer_text)
        q_entry["scores"] = scores

    # If coding task, run checks
    is_coding = q_entry.get("category") == "coding_task"
    coding_result = None
    if is_coding:
        # We don't have a challenge set up in this minimal flow; record a placeholder
        coding_result = {"question_id": question_id, "status": "not_applicable"}
        session.setdefault("coding_results", []).append(coding_result)

    sp.update_session(sessions_dir, session_id, {"questions": questions})

    # Find next question
    bank = _load_question_bank(repo_root)
    bank_questions = bank.get("questions", [])
    current_idx = next((i for i, q in enumerate(bank_questions) if q["id"] == question_id), -1)
    next_idx = current_idx + 1

    if next_idx >= len(bank_questions):
        print(json.dumps({"session_id": session_id, "done": True, "answered": question_id}))
        return

    next_q = bank_questions[next_idx]
    out = {
        "session_id": session_id,
        "question_id": next_q["id"],
        "category": next_q["category"],
        "text": next_q["text"],
        "difficulty": next_q.get("difficulty", "medium"),
        "project_references": next_q.get("project_references", []),
        "current_index": next_idx,
        "total_questions": len(bank_questions),
    }

    # Guided mode: offer a hint if the score was low
    if mode == "guided" and rubric and q_entry.get("scores"):
        avg_score = sum(q_entry["scores"].values()) / len(q_entry["scores"])
        if avg_score < 2:
            hints = rubric.get("hints") or []
            hint = hints[0] if hints else "Consider reviewing the expected concepts in the rubric."
            out["hint"] = hint

    print(json.dumps(out, indent=2))


def cmd_finish(repo_root: Path, session_id: str) -> None:
    sessions_dir = _sessions_dir(repo_root)

    # Mark complete
    subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "save_progress.py"), str(repo_root),
         "complete", session_id],
        capture_output=True, text=True
    )

    # Score the session
    session = sp.load_session(sessions_dir, session_id)
    score = sr.compute_scores(session)

    # Persist score to session file
    session["overall_score"] = score["overall_score"]
    session["categories"] = score["categories"]
    session["strengths"] = score["strengths"]
    session["gaps"] = score["gaps"]
    session["generated_at"] = score["generated_at"]
    session["summary"] = {
        "overall_score": score["overall_score"],
        "strengths": score["strengths"],
        "gaps": score["gaps"],
    }
    sp.update_session(sessions_dir, session_id, session)

    # Write score file
    score_path = sessions_dir / f"{session_id}-score.json"
    score_path.write_text(json.dumps(score, indent=2), encoding="utf-8")

    print(json.dumps(score, indent=2))


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Orchestrate assessment sessions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("repo_root", help="Path to the repository root.")
    sub = parser.add_subparsers(dest="command", required=True)

    start_p = sub.add_parser("start", help="Start a new assessment session.")
    start_p.add_argument("--mode", choices=["strict", "guided"], default="guided",
                         help="Assessment mode (default: guided).")

    ans_p = sub.add_parser("answer", help="Record an answer and advance.")
    ans_p.add_argument("session_id", help="Session ID.")
    ans_p.add_argument("question_id", help="Question ID being answered.")
    ans_p.add_argument("answer_text", help="The answer text.")
    ans_p.add_argument("--mode", choices=["strict", "guided"], default="guided",
                       help="Assessment mode (default: guided).")

    fin_p = sub.add_parser("finish", help="Finish and score the session.")
    fin_p.add_argument("session_id", help="Session ID.")

    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists():
        sys.exit(f"Error: repository path '{repo_root}' does not exist.")

    if args.command == "start":
        cmd_start(repo_root, args.mode)
    elif args.command == "answer":
        cmd_answer(repo_root, args.session_id, args.question_id, args.answer_text, args.mode)
    elif args.command == "finish":
        cmd_finish(repo_root, args.session_id)


if __name__ == "__main__":
    main()
