#!/usr/bin/env python3
"""
check_example_counts.py -- Fails when a shipped example stops detecting what it
used to detect.

`CI` already runs the pipeline over every example, which proves the scripts do not
crash. It does not prove they still see the project: a broken detector lowers the
route count, the question bank falls back to generic filler, and every step stays
green. This script is the missing assertion.

Run it after the pipeline has been run over `examples/`:

    python scripts/scan_repository.py examples/example-django-blog   # per example
    python tests/check_example_counts.py
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = REPO_ROOT / "examples"

# What each shipped example must produce. Update together with
# examples/README.md -- the two are the same claim.
EXPECTED = {
    "example-todo-app": {"routes": 7, "protected": 4, "models": 2, "min_questions": 16},
    "example-django-blog": {"routes": 15, "protected": 12, "models": 2, "min_questions": 10},
    "example-fastapi-tasks": {"routes": 7, "protected": 4, "models": 2, "min_questions": 9},
    "example-nextjs-todo": {"routes": 4, "protected": 0, "models": 0, "min_questions": 8},
}


def check_example(name: str, expected: dict) -> list:
    defense = EXAMPLES / name / ".project-defense"
    problems = []
    graph_path = defense / "project-graph.json"
    bank_path = defense / "question-bank.json"
    if not graph_path.exists():
        return ["{}: no project-graph.json -- run the pipeline over examples/ first".format(name)]
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    routes = graph.get("backend", {}).get("routes", [])
    protected = len(graph.get("auth", {}).get("protected_routes") or [])
    models = len(graph.get("data", {}).get("models", []))

    if len(routes) != expected["routes"]:
        problems.append(
            "{}: {}/{} routes detected".format(name, len(routes), expected["routes"])
        )
    if protected != expected["protected"]:
        problems.append(
            "{}: {}/{} protected routes".format(name, protected, expected["protected"])
        )
    if models != expected["models"]:
        problems.append("{}: {}/{} models detected".format(name, models, expected["models"]))
    if not bank_path.exists():
        problems.append("{}: no question-bank.json".format(name))
        return problems
    bank = json.loads(bank_path.read_text(encoding="utf-8"))
    questions = bank.get("questions", [])
    if len(questions) < expected["min_questions"]:
        problems.append(
            "{}: {} questions, expected at least {}".format(
                name, len(questions), expected["min_questions"]
            )
        )
    # A bank where every question is generic means the detectors saw nothing.
    specific = [q for q in questions if "generic" not in (q.get("rubric_id") or "")]
    if questions and not specific:
        problems.append("{}: every question is generic -- detectors found nothing".format(name))
    return problems


def main() -> int:
    problems = []
    for name, expected in EXPECTED.items():
        problems.extend(check_example(name, expected))
    if problems:
        print("Example detection regressed:", file=sys.stderr)
        for problem in problems:
            print("  - {}".format(problem), file=sys.stderr)
        print(
            "\nIf the change was intended, update EXPECTED here and the table in "
            "examples/README.md together.",
            file=sys.stderr,
        )
        return 1
    print("All {} examples still detect what they are documented to detect.".format(len(EXPECTED)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
