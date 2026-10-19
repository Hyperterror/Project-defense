#!/usr/bin/env python3
"""
score_report.py -- Score a completed assessment session against the rubric weights.

Reads sessions/<session-id>.json, applies weighted scoring across six categories:
  Architecture       15%
  Core Implementation 20%
  Independent Coding  30%
  Debugging/Failure   15%
  Trade-offs          10%
  Security/Reliability 10%

Each category score = average concept score (0-3) for all answered questions in
that category, normalized to 0.0-1.0. Weighted overall score = sum of
(category_score * weight) across all categories.

Output JSON:
  {
    "session_id": str,
    "overall_score": float (0.0-1.0),
    "categories": {
      name: {
        "score": float,
        "weight": float,
        "passed": [question_id, ...],
        "failed": [question_id, ...]
      }
    },
    "strengths": [category, ...],
    "gaps": [category, ...],
    "generated_at": ISO-8601
  }

CLI:
  python3 score_report.py <session-json-path> [--output <out.json>]

Fully deterministic — same input always produces the same output.
Stdlib only, Python 3.8+.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


# -----------------------------------------------------------------------
# Category weights (must sum to 1.0)
# -----------------------------------------------------------------------

CATEGORY_WEIGHTS: dict = {
    "Architecture": 0.15,
    "Core Implementation": 0.20,
    "Independent Coding": 0.30,
    "Debugging/Failure": 0.15,
    "Trade-offs": 0.10,
    "Security/Reliability": 0.10,
}

# Validate at import time
_weight_sum = round(sum(CATEGORY_WEIGHTS.values()), 10)
assert _weight_sum == 1.0, f"Category weights must sum to 1.0, got {_weight_sum}"


# -----------------------------------------------------------------------
# Category normalisation helpers
# -----------------------------------------------------------------------

# Map question category strings from the session to the scoring category keys.
# Multiple aliases can map to the same bucket.
_CATEGORY_ALIASES: dict = {
    "architecture": "Architecture",
    "explanation": "Architecture",
    "core_implementation": "Core Implementation",
    "core implementation": "Core Implementation",
    "independent_coding": "Independent Coding",
    "independent coding": "Independent Coding",
    "coding_task": "Independent Coding",
    "coding task": "Independent Coding",
    "debugging": "Debugging/Failure",
    "failure_scenario": "Debugging/Failure",
    "failure scenario": "Debugging/Failure",
    "debugging/failure": "Debugging/Failure",
    "trade_off": "Trade-offs",
    "trade-off": "Trade-offs",
    "trade_offs": "Trade-offs",
    "trade-offs": "Trade-offs",
    "security": "Security/Reliability",
    "security/reliability": "Security/Reliability",
    "reliability": "Security/Reliability",
}


def _normalise_category(raw: str) -> str:
    """Map a raw category string from the session to a canonical scoring bucket."""
    return _CATEGORY_ALIASES.get(raw.lower(), raw)


# -----------------------------------------------------------------------
# Scoring logic
# -----------------------------------------------------------------------

MAX_CONCEPT_SCORE = 3  # 0-3 per concept


def compute_scores(session: dict) -> dict:
    """Compute per-category and overall scores from a session dict.

    Returns a result dict matching the output schema described in the module
    docstring.  Fully deterministic.
    """
    questions = session.get("questions", [])

    # Accumulate per-category scores
    category_totals: dict = {cat: {"total": 0.0, "count": 0, "passed": [], "failed": []} for cat in CATEGORY_WEIGHTS}

    for q in questions:
        raw_cat = q.get("category", "")
        cat = _normalise_category(raw_cat)
        if cat not in CATEGORY_WEIGHTS:
            # Unknown category — ignore for scoring
            continue

        scores_map = q.get("scores", {})
        if not scores_map:
            # Question has no scores recorded — treat as 0 for every concept
            # Only count it if it has an answer (unanswered questions are skipped)
            if q.get("answer") is not None:
                category_totals[cat]["total"] += 0.0
                category_totals[cat]["count"] += 1
                category_totals[cat]["failed"].append(q.get("question_id", ""))
            continue

        # Average over all scored concepts
        concept_values = list(scores_map.values())
        avg = sum(concept_values) / len(concept_values)
        normalized = avg / MAX_CONCEPT_SCORE  # 0.0-1.0

        category_totals[cat]["total"] += normalized
        category_totals[cat]["count"] += 1

        q_id = q.get("question_id", "")
        if normalized >= 0.5:
            category_totals[cat]["passed"].append(q_id)
        else:
            category_totals[cat]["failed"].append(q_id)

    # Build per-category output
    categories = {}
    overall = 0.0
    strengths = []
    gaps = []

    for cat, weight in CATEGORY_WEIGHTS.items():
        data = category_totals[cat]
        if data["count"] > 0:
            cat_score = data["total"] / data["count"]
        else:
            cat_score = 0.0

        categories[cat] = {
            "score": round(cat_score, 6),
            "weight": weight,
            "passed": data["passed"],
            "failed": data["failed"],
        }

        overall += cat_score * weight

        if cat_score >= 0.5:
            strengths.append(cat)
        else:
            gaps.append(cat)

    return {
        "session_id": session.get("session_id", ""),
        "overall_score": round(overall, 6),
        "categories": categories,
        "strengths": strengths,
        "gaps": gaps,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Score a completed assessment session.",
    )
    parser.add_argument("session_json", help="Path to the session JSON file.")
    parser.add_argument("--output", default=None, help="Write output JSON to this path.")
    args = parser.parse_args()

    session_path = Path(args.session_json)
    if not session_path.exists():
        sys.exit(f"Error: session file '{session_path}' not found.")

    try:
        session = json.loads(session_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"Error: '{session_path}' contains invalid JSON.\nDetails: {exc}")

    result = compute_scores(session)
    output_text = json.dumps(result, indent=2)
    print(output_text)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
        print(f"Score written to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
