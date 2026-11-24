#!/usr/bin/env python3
"""
plan_review.py -- Decide which questions to re-answer today, and why.

Assessment answers test *fluency* (in-the-moment recall), which feels like
mastery but decays. Defense performance needs *storage strength*, and the only
way to build it is retrieval practice on a spaced schedule. This script turns
the sessions you already have into that schedule:

  - every question you answered gets a next-review date from a Leitner ladder
    (1, 3, 7, 16, 35 days), shortened while the score is still weak;
  - questions you never answered are due immediately;
  - the list is interleaved across categories instead of blocked, because
    mixed practice is what forces recall rather than pattern matching.

Nothing here is random: the same sessions and the same `--today` always
produce the same plan.

Usage:
    python scripts/plan_review.py <repo_root> [--today YYYY-MM-DD]
                                  [--limit N] [--write]

    --write     also write <repo_root>/.project-defense/review-plan.md

Exit codes: 0 = plan produced (even when nothing is due), 2 = no question bank.

Stdlib only, Python 3.8+.
"""

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# Leitner ladder, in days. Index = number of completed attempts.
INTERVALS = [0, 1, 3, 7, 16, 35]

# A question whose mean concept score is below this is still "weak", and its
# next review is pulled forward instead of pushed out.
WEAK_THRESHOLD = 2.0
MAX_SCORE = 3


def _parse_date(value):
    """Parse the date part of an ISO string.  Returns None when unusable."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


def _load_question_bank(repo_root: Path) -> dict:
    path = repo_root / ".project-defense" / "question-bank.json"
    if not path.exists():
        sys.exit(
            "Error: no question bank at '%s'.\n"
            "Generate it first:\n"
            "  python scripts/generate_question_bank.py %s" % (path, repo_root)
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit("Error: '%s' is not valid JSON.\nDetails: %s" % (path, exc))


def _iter_sessions(repo_root: Path):
    sessions_dir = repo_root / ".project-defense" / "sessions"
    if not sessions_dir.is_dir():
        return
    for path in sorted(sessions_dir.glob("*.json")):
        if path.name.endswith("-score.json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict) and data.get("questions"):
            yield data


def _attempts_by_question(repo_root: Path) -> dict:
    """Map question_id -> list of (date, scores dict, scored_by), oldest first."""
    attempts = {}
    for session in _iter_sessions(repo_root):
        session_date = (
            _parse_date(session.get("updated_at"))
            or _parse_date(session.get("created_at"))
        )
        for q in session.get("questions", []):
            qid = q.get("question_id")
            scores = q.get("scores") or {}
            if not qid or not scores:
                continue
            when = _parse_date(q.get("answered_at")) or session_date
            if when is None:
                continue
            attempts.setdefault(qid, []).append(
                (when, scores, q.get("scored_by", ""))
            )
    for qid in attempts:
        attempts[qid].sort(key=lambda item: item[0])
    return attempts


def _score_summary(scores: dict) -> dict:
    values = [v for v in scores.values() if isinstance(v, (int, float))]
    if not values:
        return {"mean": None, "gaps": [], "weak": True}
    mean = sum(values) / float(len(values))
    gaps = sorted(
        (name for name, score in scores.items()
         if isinstance(score, (int, float)) and score < WEAK_THRESHOLD),
        key=lambda name: scores[name],
    )
    return {"mean": mean, "gaps": gaps, "weak": mean < WEAK_THRESHOLD}


def _next_interval(attempt_count: int, weak: bool) -> int:
    index = min(max(attempt_count, 1), len(INTERVALS) - 1)
    interval = INTERVALS[index]
    if weak:
        # Pull a weak question forward: review it before it fully decays.
        interval = max(1, INTERVALS[max(index - 1, 1)])
    return interval


def build_plan(repo_root: Path, today: dt.date, limit: int = 10) -> dict:
    bank = _load_question_bank(repo_root)
    questions = bank.get("questions", [])
    attempts = _attempts_by_question(repo_root)

    entries = []
    for question in questions:
        qid = question.get("id")
        history = attempts.get(qid, [])
        entry = {
            "question_id": qid,
            "category": question.get("category", "unknown"),
            "text": question.get("text", ""),
            "attempts": len(history),
            "last_attempted": None,
            "mean_score": None,
            "concept_gaps": [],
            "reason": "",
            "due": None,
            "days_overdue": None,
        }
        if not history:
            entry["due"] = today
            entry["reason"] = "never answered"
            entries.append(entry)
            continue

        last_date, scores, scored_by = history[-1]
        summary = _score_summary(scores)
        interval = _next_interval(len(history), summary["weak"])
        due = last_date + dt.timedelta(days=interval)
        entry.update({
            "last_attempted": last_date.isoformat(),
            "mean_score": None if summary["mean"] is None
            else round(summary["mean"], 2),
            "concept_gaps": summary["gaps"],
            "due": due,
            "reason": (
                "weak (%.1f/3), review early" % summary["mean"]
                if summary["weak"] else
                "spaced review after %d attempt(s)" % len(history)
            ),
        })
        if scored_by == "heuristic":
            entry["reason"] += "; score is heuristic, not rubric-graded"
        entries.append(entry)

    due = [e for e in entries if e["due"] is not None and e["due"] <= today]
    for entry in due:
        entry["days_overdue"] = (today - entry["due"]).days

    # Interleave by category: never two questions of the same category in a row
    # while another category still has one.
    due.sort(key=lambda e: (-e["days_overdue"], e["mean_score"] or 0))
    buckets = {}
    for entry in due:
        buckets.setdefault(entry["category"], []).append(entry)
    ordered = []
    categories = sorted(buckets)
    while len(ordered) < len(due):
        for category in categories:
            bucket = buckets.get(category) or []
            if bucket:
                ordered.append(bucket.pop(0))
    if limit and limit > 0:
        ordered = ordered[:limit]

    for entry in ordered:
        entry["due"] = entry["due"].isoformat()

    return {
        "today": today.isoformat(),
        "total_questions": len(questions),
        "answered_questions": len(attempts),
        "due_count": len(due),
        "shown": len(ordered),
        "questions": ordered,
    }


def render_markdown(plan: dict) -> str:
    lines = [
        "# Review Plan",
        "",
        "Spaced retrieval over the questions you have already attempted. "
        "Answer from memory first; only then re-read notes.",
        "",
        "- Today: %s" % plan["today"],
        "- Due: %d of %d questions (%d answered so far)"
        % (plan["due_count"], plan["total_questions"], plan["answered_questions"]),
        "",
        "| # | Question | Category | Last attempt | Mean | Why it is due |",
        "|---|----------|----------|--------------|------|----------------|",
    ]
    for index, entry in enumerate(plan["questions"], start=1):
        text = " ".join(entry["text"].split())
        if len(text) > 80:
            text = text[:77] + "..."
        lines.append(
            "| %d | `%s` -- %s | %s | %s | %s | %s |"
            % (
                index,
                entry["question_id"],
                text.replace("|", "\\|"),
                entry["category"],
                entry["last_attempted"] or "never",
                "-" if entry["mean_score"] is None else "%.2f" % entry["mean_score"],
                entry["reason"].replace("|", "\\|"),
            )
        )
    gaps = [
        (entry["question_id"], gap)
        for entry in plan["questions"]
        for gap in entry["concept_gaps"]
    ]
    if gaps:
        lines += ["", "## Concepts still missing", ""]
        lines += ["- `%s` **%s**" % (qid, gap) for qid, gap in gaps]
    lines += [
        "",
        "## How to use this",
        "",
        "1. Answer each question out loud, no notes, before checking anything.",
        "2. Score it honestly against the rubric's `scoring_levels` "
        "(`save_progress.py update ... --score`).",
        "3. Questions you scored 2+ move further out on the ladder; "
        "anything below 2 comes back sooner.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Plan which assessment questions to review today."
    )
    parser.add_argument("repo_root", help="Project root that contains .project-defense/")
    parser.add_argument("--today", default=None,
                        help="Override today's date (YYYY-MM-DD), for reproducible plans")
    parser.add_argument("--limit", type=int, default=10,
                        help="Maximum questions in the plan (0 = no limit)")
    parser.add_argument("--write", action="store_true",
                        help="Also write .project-defense/review-plan.md")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.is_dir():
        sys.exit("Error: '%s' is not a directory." % repo_root)

    if args.today:
        today = _parse_date(args.today)
        if today is None:
            sys.exit(
                "Error: --today must look like YYYY-MM-DD (got %r)." % args.today
            )
    else:
        today = dt.date.today()

    plan = build_plan(repo_root, today, args.limit)

    if args.write:
        out_path = repo_root / ".project-defense" / "review-plan.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_markdown(plan), encoding="utf-8")
        # Keep stdout pure JSON so the plan can be piped into other tools.
        print("Wrote %s" % out_path, file=sys.stderr)

    print(json.dumps(plan, indent=2))
    if not args.json and plan["due_count"] == 0:
        print(
            "\nNothing is due today. Answer questions only when this plan says "
            "so: cramming the same question daily builds fluency, not recall.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
