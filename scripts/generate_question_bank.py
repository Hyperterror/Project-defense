#!/usr/bin/env python3
"""
generate_question_bank.py -- Generate project-specific interview questions.

CLI:
  python3 generate_question_bank.py <repo_path>

Reads .project-defense/project-graph.json and generates questions in 4 categories:
  - explanation     (architecture/components)
  - failure_scenario (what happens when X fails)
  - trade_off        (why X was chosen over Y)
  - coding_task      (implement/fix a function)

Each question: { id, category, text, rubric_id, difficulty, project_references: [{file, lines}] }

Writes:
  .project-defense/question-bank.json
  .project-defense/question-bank.md

Stdlib only, Python 3.8+.
"""

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RUBRICS_DIR = SCRIPT_DIR.parent / "rubrics"

# Category prefix for question IDs
_CATEGORY_PREFIX = {
    "explanation": "e",
    "failure_scenario": "f",
    "trade_off": "t",
    "coding_task": "c",
}

_DIFFICULTIES = ["easy", "medium", "hard"]


# -----------------------------------------------------------------------
# Graph entry iteration
# -----------------------------------------------------------------------

def _iter_named_entries(graph: dict):
    """Yield (section_name, entry_dict) for entries that have a 'name' field."""
    for section_key, section_val in graph.items():
        if isinstance(section_val, dict):
            for sub_key, sub_list in section_val.items():
                if isinstance(sub_list, list):
                    for entry in sub_list:
                        if isinstance(entry, dict) and entry.get("name"):
                            yield section_key, entry
        elif isinstance(section_val, list):
            for entry in section_val:
                if isinstance(entry, dict) and entry.get("name"):
                    yield section_key, entry


def _importers(graph: dict, target_file: str) -> list:
    """Return the files that import target_file, per the graph's relationships."""
    norm = (target_file or "").replace("\\", "/")
    importers = []
    for edge in graph.get("relationships", []) or []:
        if edge.get("type") != "imports":
            continue
        if (edge.get("to") or "").replace("\\", "/") == norm:
            source = edge.get("from", "")
            if source and source not in importers:
                importers.append(source)
    return importers


def _iter_entries_with_key(graph: dict):
    """Yield (section_key, sub_key, entry) for every list entry of the graph."""
    for section_key, section_val in graph.items():
        if not isinstance(section_val, dict):
            continue
        for sub_key, sub_list in section_val.items():
            if not isinstance(sub_list, list):
                continue
            for entry in sub_list:
                if isinstance(entry, dict):
                    yield section_key, sub_key, entry


MODULE_KEYS = (
    "services", "controllers", "middleware", "state_management", "components",
)


def _module_candidates(graph: dict):
    """Yield (priority, name, entry) for entries that behave like a module.

    Bare package mounts (`app.use(cors())`) are named in lower case and carry no
    `details.type`; real modules in this graph are camelCase/PascalCase
    (`authMiddleware`, `useAuth`, `TodoItem`) and often carry a type.
    """
    for _section, sub_key, entry in _iter_entries_with_key(graph):
        if sub_key not in MODULE_KEYS:
            continue
        name = str(entry.get("name", "")).strip()
        if not name or not entry.get("evidence", {}).get("file"):
            continue
        has_type = bool(entry.get("details", {}).get("type"))
        if not has_type and name.islower():
            continue
        yield MODULE_KEYS.index(sub_key), name, entry


def _ref_from_evidence(entry: dict) -> list:
    ev = entry.get("evidence", {})
    if not ev.get("file"):
        return []
    return [{"file": ev["file"], "lines": ev.get("lines", [1, 1])}]


# -----------------------------------------------------------------------
# Rubric matching
# -----------------------------------------------------------------------

def _load_rubrics() -> dict:
    """Map question ids and categories to candidate rubrics.

    Values are lists of (rubric_id, topic_keywords): a question id can carry
    several rubrics, and a category can carry one or more fallbacks -- a
    topic-bearing fallback (e.g. module-depth) only applies when its keywords
    appear in the question text, otherwise the topic-less generic fallback wins.
    Files are read in sorted order, so ties resolve deterministically.
    """
    mapping = {}
    if not RUBRICS_DIR.exists():
        return mapping
    for path in sorted(RUBRICS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rubric_id = data.get("id", path.stem)
        topics = [t.lower() for t in data.get("topic", []) or []]
        qid = data.get("question_id")
        if qid and qid != "generic":
            mapping.setdefault(qid, []).append((rubric_id, topics))
        category = data.get("category")
        if category:
            mapping.setdefault("category:" + category, []).append((rubric_id, topics))
    return mapping


def _rubric_for(rubrics_map: dict, question_id: str, category: str,
                question_text: str = "") -> str:
    """Pick the rubric that actually fits this question.

    Order: a question-specific rubric whose `topic` keywords appear in the
    question text, then the most specific category fallback (topic keywords
    matched), then the topic-less generic fallback. Every generated question
    ends up gradeable, and an auth rubric never grades a todo question.
    """
    text = (question_text or "").lower()

    def _matches(candidates):
        for rubric_id, topics in candidates:
            if topics and any(t in text for t in topics):
                return rubric_id
        return None

    specific = _matches(rubrics_map.get(question_id) or [])
    if specific:
        return specific
    by_id = rubrics_map.get(question_id) or []
    if by_id:
        untopiced = [rid for rid, topics in by_id if not topics]
        if untopiced:
            return untopiced[0]

    fallbacks = rubrics_map.get("category:" + category) or []
    targeted = _matches(fallbacks)
    if targeted:
        return targeted
    generic = [rid for rid, topics in fallbacks if not topics]
    if generic:
        return generic[0]
    return fallbacks[0][0] if fallbacks else None


# -----------------------------------------------------------------------
# Question generators
# -----------------------------------------------------------------------

def gen_explanation_questions(graph: dict, rubrics_map: dict) -> list:
    """One explanation question per top-level graph section that has entries.

    Plus one deletion-test question per module-like entry (max 2): 'if you
    deleted this, what would break?' separates modules that earn their keep
    from pass-throughs, and interviewers ask it constantly.
    """
    questions = []
    idx = 1
    seen = set()
    for section, entry in _iter_named_entries(graph):
        if section in seen:
            continue
        seen.add(section)
        name = entry.get("name", section)
        ev_file = entry.get("evidence", {}).get("file", "")
        text = f"Walk me through the `{name}` in `{ev_file}`. What does it do and how does it fit into the architecture?"
        qid = f"q-e{idx:03d}"
        questions.append({
            "id": qid,
            "category": "explanation",
            "text": text,
            "rubric_id": _rubric_for(rubrics_map, qid, "explanation", text),
            "difficulty": "medium",
            "project_references": _ref_from_evidence(entry),
        })
        idx += 1

    # Deletion-test questions: prefer modules whose file actually has importers
    # (that is what makes the question answerable with evidence), then by
    # section priority: services, controllers, middleware, hooks, components.
    ranked = []
    for priority, name, entry in _module_candidates(graph):
        ev_file = entry.get("evidence", {}).get("file", "")
        ranked.append((len(_importers(graph, ev_file)), -priority, name, entry))
    ranked.sort(key=lambda item: (-item[0], item[1]))

    picked = []
    seen_names = set()
    for _importers_count, _priority, name, entry in ranked:
        if name in seen_names:
            continue
        seen_names.add(name)
        picked.append((entry, name))
        if len(picked) == 2:
            break

    for entry, name in picked:
        ev_file = entry.get("evidence", {}).get("file", "")
        importers = _importers(graph, ev_file)
        if importers:
            joined = ", ".join("`%s`" % imp for imp in importers[:4])
            more = " and %d more" % (len(importers) - 4) if len(importers) > 4 else ""
            dependency_clause = (
                "The graph shows %d direct importer(s): %s%s."
                % (len(importers), joined, more)
            )
        else:
            dependency_clause = (
                "No other file imports it directly, so say whether anything "
                "reaches it indirectly."
            )
        text = (
            f"If `{name}` in `{ev_file}` were deleted entirely, what would break "
            "and what would have to be reimplemented elsewhere? "
            f"{dependency_clause} Is it a deep module or a pass-through?"
        )
        qid = f"q-e{idx:03d}"
        questions.append({
            "id": qid,
            "category": "explanation",
            "text": text,
            "rubric_id": _rubric_for(rubrics_map, qid, "explanation", text),
            "difficulty": "hard",
            "project_references": _ref_from_evidence(entry),
        })
        idx += 1

    return questions


def gen_failure_questions(graph: dict, rubrics_map: dict) -> list:
    """Two kinds of failure question.

    1. 'What happens when X fails?' -- one per risk/uncertainty (max 5), which
       probes knowledge of the failure path.
    2. 'How would you find the cause?' -- one for the top 2 risks, which probes
       the diagnosis discipline: build a loop, minimise, hypothesise, instrument,
       lock it down with a regression test.
    """
    questions = []
    idx = 1

    for risk in graph.get("risks", []):
        if idx > 5:
            break
        desc = risk.get("description", "an error occurs")
        text = f"What happens in your application when {desc.lower()}? Walk me through the failure path."
        qid = f"q-f{idx:03d}"
        questions.append({
            "id": qid,
            "category": "failure_scenario",
            "text": text,
            "rubric_id": _rubric_for(rubrics_map, qid, "failure_scenario", text),
            "difficulty": "hard",
            "project_references": _ref_from_evidence(risk),
        })
        idx += 1

    for unc in graph.get("uncertainties", []):
        if idx > 5:
            break
        question_text = unc.get("question", "What happens if a dependency fails?")
        qid = f"q-f{idx:03d}"
        questions.append({
            "id": qid,
            "category": "failure_scenario",
            "text": question_text,
            "rubric_id": _rubric_for(rubrics_map, qid, "failure_scenario", question_text),
            "difficulty": "hard",
            "project_references": _ref_from_evidence(unc),
        })
        idx += 1

    for risk in graph.get("risks", [])[:2]:
        raw = str(risk.get("description", "something breaks in production")).strip()
        raw = raw.rstrip(".").strip()
        symptom = raw[:1].upper() + raw[1:] if raw else "Something breaks in production"
        text = (
            f"A symptom is reported: {symptom}. You cannot name the cause from the "
            "code alone. Walk me through how you would find the cause: the loop "
            "you would build first, what you would cut from it, and how you "
            "would prove the fix."
        )
        qid = f"q-f{idx:03d}"
        questions.append({
            "id": qid,
            "category": "failure_scenario",
            "text": text,
            "rubric_id": _rubric_for(rubrics_map, qid, "failure_scenario", text),
            "difficulty": "hard",
            "project_references": _ref_from_evidence(risk),
        })
        idx += 1

    return questions


def gen_tradeoff_questions(graph: dict, rubrics_map: dict) -> list:
    """One per stack technology pair + one per auth strategy choice."""
    questions = []
    idx = 1

    stack = graph.get("project", {}).get("stack", [])
    if len(stack) >= 2:
        for i in range(len(stack) - 1):
            a, b = stack[i], stack[i + 1]
            text = f"Why did you choose {a} over the obvious alternative? What trade-offs did you accept?"
            qid = f"q-t{idx:03d}"
            questions.append({
                "id": qid,
                "category": "trade_off",
                "text": text,
                "rubric_id": _rubric_for(rubrics_map, qid, "trade_off", text),
                "difficulty": "medium",
                "project_references": [],
            })
            idx += 1

    auth_strategy = graph.get("auth", {}).get("strategy", "")
    if auth_strategy and auth_strategy != "none":
        text = f"Explain your choice of {auth_strategy} for authentication. Why not an alternative like session-based or OAuth?"
        qid = f"q-t{idx:03d}"
        questions.append({
            "id": qid,
            "category": "trade_off",
            "text": text,
            "rubric_id": _rubric_for(rubrics_map, qid, "trade_off", text),
            "difficulty": "medium",
            "project_references": [],
        })
        idx += 1

    return questions


def gen_coding_questions(graph: dict, rubrics_map: dict) -> list:
    """One per backend route + one generic test-writing question if no rubric is linked."""
    questions = []
    idx = 1

    routes = graph.get("backend", {}).get("routes", [])
    for route in routes:
        handler = route.get("handler", "the route")
        method = route.get("method", "GET")
        path = route.get("path", "/")
        text = f"Implement or explain the logic behind the {method} {path} handler (`{handler}`). What does it need to do and what edge cases should it handle?"
        qid = f"q-c{idx:03d}"
        questions.append({
            "id": qid,
            "category": "coding_task",
            "text": text,
            "rubric_id": _rubric_for(rubrics_map, qid, "coding_task", text),
            "difficulty": "hard",
            "project_references": _ref_from_evidence(route),
        })
        idx += 1

    # Generic test-writing question
    text = "Write a test for one of the core functions in this project. What would you test and why?"
    qid = f"q-c{idx:03d}"
    questions.append({
        "id": qid,
        "category": "coding_task",
        "text": text,
        "rubric_id": _rubric_for(rubrics_map, qid, "coding_task", text),
        "difficulty": "medium",
        "project_references": [],
    })
    return questions


# -----------------------------------------------------------------------
# Markdown rendering
# -----------------------------------------------------------------------

def render_markdown(questions: list) -> str:
    lines = ["# Question Bank", "", "Project-specific interview questions generated from the project graph.", ""]
    by_cat = {
        "explanation": "Explanation Questions",
        "failure_scenario": "Failure Scenario Questions",
        "trade_off": "Trade-off Questions",
        "coding_task": "Coding Task Questions",
    }
    for cat, header in by_cat.items():
        cat_qs = [q for q in questions if q["category"] == cat]
        if not cat_qs:
            continue
        lines.append(f"## {header}")
        lines.append("")
        for q in cat_qs:
            lines.append(f"### {q['id']} ({q['difficulty']})")
            lines.append("")
            lines.append(f"**Question:** {q['text']}")
            lines.append("")
            if q.get("rubric_id"):
                lines.append(f"*Rubric: {q['rubric_id']}*")
                lines.append("")
            if q.get("project_references"):
                refs = ", ".join(f"{r['file']}" + (f":{r['lines'][0]}" if r.get("lines") else "") for r in q["project_references"])
                lines.append(f"*References: {refs}*")
                lines.append("")
            lines.append("---")
            lines.append("")
    return "\n".join(lines)


# -----------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------


def generate_question_bank(repo_root: Path) -> dict:
    """Generate the question bank and write JSON + MD files.  Returns the question list."""
    graph_path = repo_root / ".project-defense" / "project-graph.json"
    if not graph_path.exists():
        sys.exit(
            f"Error: '{graph_path}' not found. "
            "Run scan_repository.py, detect_code_facts.py, and build_graph.py first."
        )
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"Error: '{graph_path}' contains invalid JSON.\nDetails: {exc}")

    rubrics_map = _load_rubrics()

    questions = []
    questions.extend(gen_explanation_questions(graph, rubrics_map))
    questions.extend(gen_failure_questions(graph, rubrics_map))
    questions.extend(gen_tradeoff_questions(graph, rubrics_map))
    questions.extend(gen_coding_questions(graph, rubrics_map))

    bank = {"questions": questions}
    defense_dir = repo_root / ".project-defense"
    defense_dir.mkdir(parents=True, exist_ok=True)
    (defense_dir / "question-bank.json").write_text(json.dumps(bank, indent=2), encoding="utf-8")
    (defense_dir / "question-bank.md").write_text(render_markdown(questions), encoding="utf-8")

    return bank


def main():
    parser = argparse.ArgumentParser(
        description="Generate project-specific interview questions."
    )
    parser.add_argument("repo_path", help="Path to the repository root.")
    args = parser.parse_args()

    repo_root = Path(args.repo_path).resolve()
    if not repo_root.exists():
        sys.exit(f"Error: repository path '{repo_root}' does not exist.")

    bank = generate_question_bank(repo_root)
    print(f"Generated {len(bank['questions'])} questions.")
    print(f"  JSON: {repo_root / '.project-defense' / 'question-bank.json'}")
    print(f"  MD:   {repo_root / '.project-defense' / 'question-bank.md'}")


if __name__ == "__main__":
    main()
