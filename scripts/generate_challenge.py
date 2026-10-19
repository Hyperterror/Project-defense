#!/usr/bin/env python3
"""
generate_challenge.py -- Generate a coding challenge from the project graph.

CLI:
  python3 generate_challenge.py <repo_path> --feature <feature> --type <type> --difficulty <level>

Types: function_reconstruction, bug_fix, test_writing
Difficulties: easy, medium, hard

Reads .project-defense/project-graph.json, locates the matching feature entry,
creates a challenge manifest and starter files in:
  .project-defense/challenges/<challenge-id>/manifest.json
  .project-defense/challenges/<challenge-id>/starter/<files>

NEVER modifies original repository files.
Stdlib only, Python 3.8+.
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = SCRIPT_DIR.parent / "templates" / "challenge.schema.json"

# Allowed challenge types
VALID_TYPES = {"function_reconstruction", "bug_fix", "test_writing"}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}


# -----------------------------------------------------------------------
# Schema validation helper (uses validate_graph if available)
# -----------------------------------------------------------------------

def _load_validate():
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        from validate_graph import validate_value
        return validate_value
    except ImportError:
        return None


# -----------------------------------------------------------------------
# Graph search
# -----------------------------------------------------------------------

def _iter_entries(graph: dict):
    """Yield (section_name, entry_dict) for every entry in the graph."""
    for section_key, section_val in graph.items():
        if isinstance(section_val, dict):
            for sub_key, sub_list in section_val.items():
                if isinstance(sub_list, list):
                    for entry in sub_list:
                        if isinstance(entry, dict):
                            yield section_key, entry
        elif isinstance(section_val, list):
            for entry in section_val:
                if isinstance(entry, dict):
                    yield section_key, entry


def find_feature_entry(graph: dict, feature: str) -> dict | None:
    """Find the first graph entry whose name or details text contains feature (case-insensitive)."""
    feature_lower = feature.lower()
    for _, entry in _iter_entries(graph):
        name = str(entry.get("name", "")).lower()
        details_text = json.dumps(entry.get("details", {})).lower()
        if feature_lower in name or feature_lower in details_text:
            return entry
    return None


# -----------------------------------------------------------------------
# Git revision
# -----------------------------------------------------------------------

def _get_git_revision(repo_root: Path) -> str:
    """Return current HEAD commit hash, or 'unversioned'."""
    head_file = repo_root / ".git" / "HEAD"
    if not head_file.exists():
        return "unversioned"
    try:
        head_content = head_file.read_text(encoding="utf-8").strip()
        if head_content.startswith("ref: "):
            ref = head_content[5:]
            ref_file = repo_root / ".git" / ref
            if ref_file.exists():
                return ref_file.read_text(encoding="utf-8").strip()
        # Detached HEAD — content is the hash itself
        if re.match(r"^[0-9a-f]{40}$", head_content):
            return head_content
    except Exception:
        pass
    return "unversioned"


# -----------------------------------------------------------------------
# Challenge ID
# -----------------------------------------------------------------------

def _make_challenge_id(feature: str, challenge_type: str, difficulty: str, timestamp: int) -> str:
    raw = f"{feature}|{challenge_type}|{difficulty}|{timestamp}"
    return "challenge-" + hashlib.sha256(raw.encode()).hexdigest()[:8]


# -----------------------------------------------------------------------
# Starter file creation
# -----------------------------------------------------------------------

_TODO_STUB = "    # TODO: implement\n    raise NotImplementedError\n"


def _stub_function_body(source_text: str) -> str:
    """Replace function bodies with # TODO stubs.
    Works for simple def/async def blocks by indentation heuristic.
    """
    lines = source_text.splitlines(keepends=True)
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if stripped.startswith("def ") or stripped.startswith("async def "):
            result.append(line)
            indent = len(line) - len(line.lstrip())
            body_indent = indent + 4
            i += 1
            # Skip docstring if present
            if i < len(lines):
                next_stripped = lines[i].strip()
                if next_stripped.startswith('"""') or next_stripped.startswith("'''"):
                    quote = next_stripped[:3]
                    result.append(lines[i])
                    i += 1
                    # Multi-line docstring
                    while i < len(lines) and quote not in lines[i][len(line) - len(line.lstrip()):]:
                        result.append(lines[i])
                        i += 1
                    if i < len(lines):
                        result.append(lines[i])
                        i += 1
            # Skip body lines
            while i < len(lines):
                body_line = lines[i]
                if body_line.strip() == "":
                    i += 1
                    continue
                current_indent = len(body_line) - len(body_line.lstrip())
                if current_indent > indent:
                    i += 1  # skip body line
                else:
                    break
            result.append(" " * body_indent + "# TODO: implement\n")
            result.append(" " * body_indent + "raise NotImplementedError\n")
        else:
            result.append(line)
            i += 1
    return "".join(result)


def _introduce_bug(source_text: str) -> str:
    """Introduce one controlled defect in the source."""
    lines = source_text.splitlines(keepends=True)
    # Strategy 1: flip a comparison operator
    for i, line in enumerate(lines):
        if " == " in line and "def " not in line:
            lines[i] = line.replace(" == ", " != ", 1)
            return "".join(lines)
    # Strategy 2: change a status code
    for i, line in enumerate(lines):
        if "201" in line:
            lines[i] = line.replace("201", "200", 1)
            return "".join(lines)
    # Strategy 3: off-by-one in a numeric literal
    for i, line in enumerate(lines):
        m = re.search(r"\b(\d+)\b", line)
        if m and m.group(1) not in ("0", "1"):
            val = int(m.group(1))
            lines[i] = line[:m.start()] + str(val - 1) + line[m.end():]
            return "".join(lines)
    # Fallback: add a pass as first statement inside first function
    for i, line in enumerate(lines):
        if line.lstrip().startswith("def ") or line.lstrip().startswith("async def "):
            if i + 1 < len(lines):
                indent = len(lines[i]) - len(lines[i].lstrip()) + 4
                lines.insert(i + 1, " " * indent + "return None  # BUG: premature return\n")
                return "".join(lines)
    return "".join(lines)


def _generate_test_skeleton(source_text: str, source_file: str) -> str:
    """Generate a minimal test stub for a source file."""
    module_name = Path(source_file).stem
    functions = re.findall(r"^def (\w+)\(", source_text, re.MULTILINE)
    lines = [
        "import unittest",
        "",
        f"# Tests for {source_file}",
        "# TODO: fill in the test bodies",
        "",
        "",
        f"class Test{module_name.title().replace('_', '')}(unittest.TestCase):",
        "",
    ]
    if functions:
        for fn in functions[:5]:  # limit to first 5 functions
            lines.append(f"    def test_{fn}(self):")
            lines.append(f"        # TODO: test {fn}")
            lines.append("        self.fail('not implemented')")
            lines.append("")
    else:
        lines.append("    def test_placeholder(self):")
        lines.append("        # TODO: add tests")
        lines.append("        self.fail('not implemented')")
        lines.append("")

    lines += ["", "if __name__ == '__main__':", "    unittest.main()", ""]
    return "\n".join(lines)


# -----------------------------------------------------------------------
# Main generation logic
# -----------------------------------------------------------------------

def generate_challenge(repo_root: Path, feature: str, challenge_type: str, difficulty: str,
                       timestamp: int = None) -> str:
    """Create the challenge manifest and starter files.  Returns the challenge_id."""
    if timestamp is None:
        timestamp = int(time.time())

    defense_dir = repo_root / ".project-defense"
    graph_path = defense_dir / "project-graph.json"

    if not graph_path.exists():
        sys.exit(
            f"Error: '{graph_path}' not found. "
            "Run scan_repository.py, detect_code_facts.py, and build_graph.py first."
        )

    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"Error: '{graph_path}' contains invalid JSON.\nDetails: {exc}")

    entry = find_feature_entry(graph, feature)

    # Build challenge_id
    challenge_id = _make_challenge_id(feature, challenge_type, difficulty, timestamp)
    challenge_dir = defense_dir / "challenges" / challenge_id
    starter_dir = challenge_dir / "starter"
    challenge_dir.mkdir(parents=True, exist_ok=True)
    starter_dir.mkdir(parents=True, exist_ok=True)

    # Source reference from graph entry
    source_refs = []
    source_file = None
    if entry:
        ev = entry.get("evidence", {})
        if ev.get("file"):
            source_file = ev["file"]
            source_refs = [{
                "file": ev["file"],
                "lines": ev.get("lines", [1, 1]),
                "description": entry.get("name", feature),
            }]
    # Fallback: create a stub source file
    if not source_file:
        source_file = f"{feature.lower().replace(' ', '_')}.py"
        source_refs = [{
            "file": source_file,
            "lines": [1, 10],
            "description": f"Generated stub for {feature}",
        }]

    # Get repo revision
    repository_revision = _get_git_revision(repo_root)

    # Build objectives
    entry_name = entry.get("name", feature) if entry else feature
    objectives = {
        "function_reconstruction": f"Recreate `{entry_name}` from scratch without looking at the original.",
        "bug_fix": f"Fix the broken implementation of `{entry_name}` so all checks pass.",
        "test_writing": f"Write tests for `{entry_name}` that cover the listed acceptance criteria.",
    }
    objective = objectives[challenge_type]

    # Build hints from entry details
    details_text = json.dumps(entry.get("details", {})) if entry else ""
    hints = [
        f"Hint 1: Read the function signature in {source_file} carefully.",
        f"Hint 2: Focus on the input types and expected return value for `{entry_name}`.",
        f"Hint 3: Consider the edge cases — what happens with empty or invalid input? Details: {details_text[:100]}",
        f"Hint 4: Look at the evidence excerpt in the graph for `{entry_name}` to understand the expected behavior.",
    ]

    # Starter file name
    source_stem = Path(source_file).stem
    source_suffix = Path(source_file).suffix or ".py"
    starter_file_name = f"{source_stem}_starter{source_suffix}"

    # Create starter file content
    original_path = repo_root / source_file
    if original_path.exists():
        original_text = original_path.read_text(encoding="utf-8", errors="replace")
    else:
        original_text = f"# Stub for {source_file}\n\ndef {entry_name.lower().replace(' ', '_')}():\n    pass\n"

    if challenge_type == "function_reconstruction":
        starter_content = _stub_function_body(original_text)
    elif challenge_type == "bug_fix":
        starter_content = _introduce_bug(original_text)
    else:  # test_writing
        starter_content = _generate_test_skeleton(original_text, source_file)
        starter_file_name = f"test_{source_stem}{source_suffix}"

    starter_file_path = starter_dir / starter_file_name
    starter_file_path.write_text(starter_content, encoding="utf-8")

    # Build workspace section
    workspace = {
        "allowed_files": [starter_file_name],
        "starter_file": starter_file_name,
    }

    # Build checks
    checks = [
        {
            "id": "check-syntax",
            "description": "Verify the file has no syntax errors.",
            "command": ["python3", "-c", f"import ast, sys; ast.parse(open('{starter_file_name}').read()); sys.exit(0)"],
            "expected_exit_code": 0,
            "timeout_seconds": 10,
        }
    ]

    # Assemble manifest
    manifest = {
        "challenge_id": challenge_id,
        "repository_revision": repository_revision,
        "feature": feature,
        "type": challenge_type,
        "difficulty": difficulty,
        "source_references": source_refs,
        "objective": objective,
        "workspace": workspace,
        "checks": checks,
        "hint_policy": {
            "reveal_after_attempts": 2,
            "max_hints": 4,
        },
        "hints": hints,
        "status": "pending",
    }

    # Validate against schema
    validate_value = _load_validate()
    if validate_value is not None and SCHEMA_PATH.exists():
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        errors = validate_value(manifest, schema, schema)
        if errors:
            sys.exit(
                f"Error: generated manifest has {len(errors)} schema violation(s):\n"
                + "\n".join(f"  - {e}" for e in errors[:10])
            )

    manifest_path = challenge_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return challenge_id


def main():
    parser = argparse.ArgumentParser(description="Generate a coding challenge from the project graph.")
    parser.add_argument("repo_path", help="Path to the repository root.")
    parser.add_argument("--feature", required=True, help="Feature name to focus the challenge on.")
    parser.add_argument("--type", dest="challenge_type", required=True,
                        choices=list(VALID_TYPES), help="Challenge type.")
    parser.add_argument("--difficulty", required=True,
                        choices=list(VALID_DIFFICULTIES), help="Difficulty level.")
    args = parser.parse_args()

    repo_root = Path(args.repo_path).resolve()
    if not repo_root.exists():
        sys.exit(f"Error: repository path '{repo_root}' does not exist.")

    challenge_id = generate_challenge(repo_root, args.feature, args.challenge_type, args.difficulty)
    print(f"Challenge created: {challenge_id}")
    print(f"Manifest: {repo_root / '.project-defense' / 'challenges' / challenge_id / 'manifest.json'}")


if __name__ == "__main__":
    main()
