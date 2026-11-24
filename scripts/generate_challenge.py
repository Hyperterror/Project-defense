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
from typing import Optional

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


def find_feature_entry(graph: dict, feature: str) -> Optional[dict]:
    """Find the first graph entry that matches *feature*.

    Matching is case-insensitive and checks the entry's name, its route
    fields (method, path, handler), its details, and its evidence file. This
    lets `--feature "login"`, `--feature "/api/todos"` and
    `--feature "server/routes/todos.js"` all resolve to a real entry instead
    of falling back to a fabricated stub.
    """
    feature_lower = feature.lower().strip().replace("\\", "/")
    if not feature_lower:
        return None

    # Rank the fields: a name/path/handler hit identifies the feature itself,
    # while `details` and the evidence path are prose that merely mentions it.
    # Without the ranking, `--feature "api/todos"` resolved to a page component
    # whose fetch call pointed at that URL instead of the route itself.
    exact_routes, named, weak = [], [], []
    wanted = "/" + feature_lower.strip("/")
    for _section, entry in _iter_entries(graph):
        is_route = "method" in entry and "path" in entry
        path = str(entry.get("path", "")).lower()
        name = str(entry.get("name", "")).lower().replace("\\", "/")
        handler = str(entry.get("handler", "")).lower().replace("\\", "/")
        if is_route and wanted == path:
            exact_routes.append(entry)
        elif feature_lower in name or feature_lower in handler or feature_lower in path:
            named.append(entry)
        else:
            haystacks = [
                str(entry.get("method", "")),
                json.dumps(entry.get("details", {})),
                str(entry.get("evidence", {}).get("file", "")),
            ]
            if any(feature_lower in h.lower().replace("\\", "/") for h in haystacks):
                weak.append(entry)
    for bucket in (exact_routes, named, weak):
        if bucket:
            return bucket[0]
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

def _safe_ident(name: str) -> str:
    """Turn an arbitrary feature name into a valid snake_case identifier."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(name)).strip("_").lower()
    if not cleaned:
        return "feature"
    if cleaned[0].isdigit():
        cleaned = "f_" + cleaned
    return cleaned


# A definition we could practise on: def/class/function/const/export.
RE_HANDLER_DEF = re.compile(
    r"^[ 	]*(?:export[ 	]+)?(?:async[ 	]+)?(?:def|class|function)[ 	]+([A-Za-z_$][\w$]*)",
    re.M,
)


def _has_function_bodies(text: str, suffix: str) -> bool:
    """True when stubbing this text would actually remove something."""
    try:
        return _stub_source(text, suffix).strip() != text.strip()
    except Exception:
        return False


def locate_handler(repo_root: Path, entry_name: str, prefer_file: Optional[str] = None) -> Optional[str]:
    """Find the file that *defines* a graph entry's handler.

    A route's evidence points at where it is declared, which is not always
    where it is implemented: a Django URLconf points at `urls.py` while
    `PostViewSet` lives in `views.py`, and a Next.js route is a file name
    rather than a function. Practising on the declaration file would mean
    practising on a routing table, so the defining file is preferred when one
    exists.
    """
    if not entry_name:
        return None
    parts = [part.strip() for part in str(entry_name).split(".") if part.strip()]
    candidates = [part for part in reversed(parts) if part]
    if not candidates:
        return None

    try:
        from path_filters import load_ignore_patterns, walk_files
        from detect_code_facts import is_source_file
    except ImportError:
        return None

    source_files = [
        path for path in walk_files(repo_root, load_ignore_patterns(repo_root))
        if is_source_file(path)
    ]

    for name in candidates:
        if not re.match(r"^[A-Za-z_$][\w$]*$", name):
            continue
        for path in sorted(source_files):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in RE_HANDLER_DEF.finditer(text):
                if match.group(1) != name:
                    continue
                rel = str(path.relative_to(repo_root))
                if _has_function_bodies(text, path.suffix):
                    return rel
    return None


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
# JavaScript / TypeScript support
# -----------------------------------------------------------------------

JS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

# Function declaration OR arrow function assigned to a binding.
# Captures the text up to (not including) the opening brace of the body.
RE_JS_FUNCTION = re.compile(
    r"(?P<head>(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s*\*?\s*[A-Za-z_$][\w$]*\s*\([^)]*\)\s*)\{"
    r"|(?P<head2>(?:export\s+)?(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*(?:async\s+)?(?:function\s*[A-Za-z_$]*\s*\([^)]*\)|\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*)\{",
    re.DOTALL,
)


def _skip_js_string(text: str, i: int) -> int:
    """Return the index just past the JS string literal starting at i."""
    quote = text[i]
    i += 1
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == quote:
            return i + 1
        i += 1
    return i


def _skip_js_template(text: str, i: int) -> int:
    """Return the index just past the template literal starting at i."""
    i += 1
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "`":
            return i + 1
        if ch == "$" and i + 1 < len(text) and text[i + 1] == "{":
            i = _find_matching_brace(text, i + 1)
            if i < 0:
                return len(text)
            i += 1
            continue
        i += 1
    return i


def _find_matching_brace(text: str, open_idx: int) -> int:
    """Find the closing brace matching text[open_idx] == '{'.

    Skips braces inside strings, template literals and comments so that real
    source files do not produce a truncated replacement.
    """
    depth = 0
    i = open_idx
    while i < len(text):
        ch = text[i]
        if ch in ("'", '"'):
            i = _skip_js_string(text, i)
            continue
        if ch == "`":
            i = _skip_js_template(text, i)
            continue
        if ch == "/" and i + 1 < len(text):
            if text[i + 1] == "/":
                nl = text.find("\n", i)
                i = len(text) if nl < 0 else nl
                continue
            if text[i + 1] == "*":
                end = text.find("*/", i + 2)
                i = len(text) if end < 0 else end + 2
                continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _js_indent_of_line(text: str, idx: int) -> str:
    """Return the leading whitespace of the line containing idx."""
    line_start = text.rfind("\n", 0, idx) + 1
    line = text[line_start:idx]
    return line[: len(line) - len(line.lstrip())]


def _js_code_mask(text: str) -> str:
    """Return text with string and comment content blanked out (same length).

    Regex searches run against the mask so a match can never land inside a
    string literal or a comment, while offsets stay valid for the original
    text.
    """
    chars = list(text)
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in ("'", '"'):
            end = _skip_js_string(text, i)
        elif ch == "`":
            end = _skip_js_template(text, i)
        elif ch == "/" and i + 1 < n and text[i + 1] == "/":
            nl = text.find("\n", i)
            end = n if nl < 0 else nl
        elif ch == "/" and i + 1 < n and text[i + 1] == "*":
            close = text.find("*/", i + 2)
            end = n if close < 0 else close + 2
        else:
            i += 1
            continue
        for k in range(i, min(end, n)):
            if chars[k] != "\n":
                chars[k] = " "
        i = end
    return "".join(chars)


RE_JS_ARROW_BODY = re.compile(r"=>\s*\{")


def _stub_js_arrow_bodies(source_text: str) -> str:
    """Stub the block body of every arrow function, including callbacks.

    Route handlers, middleware and promise chains are almost always written as
    arrow functions passed as arguments (`app.get("/x", (req, res) => {...})`),
    which the declaration-based pass cannot see. Without this pass such a file
    is shipped verbatim as its own starter -- i.e. the solution.
    """
    mask = _js_code_mask(source_text)
    candidates = []
    for m in RE_JS_ARROW_BODY.finditer(mask):
        open_idx = m.end() - 1
        close_idx = _find_matching_brace(source_text, open_idx)
        if close_idx < 0:
            continue
        candidates.append((open_idx, close_idx))

    # Drop nested spans: replacing an outer body already removes the inner one.
    spans = []
    for open_idx, close_idx in candidates:
        if any(outer_open < open_idx < outer_close for outer_open, outer_close in spans):
            continue
        spans = [s for s in spans if not (open_idx < s[0] < close_idx)]
        spans.append((open_idx, close_idx))

    result = source_text
    for open_idx, close_idx in sorted(spans, reverse=True):
        indent = _js_indent_of_line(source_text, open_idx)
        body_indent = indent + "  "
        new_body = (
            "\n"
            + body_indent + "// TODO: implement\n"
            + body_indent + 'throw new Error("Not implemented");\n'
            + indent
        )
        result = result[: open_idx + 1] + new_body + result[close_idx:]
    return result


def _stub_js_bodies(source_text: str) -> str:
    """Replace JavaScript/TypeScript function bodies with TODO stubs.

    Imports, constants and the function signatures are preserved so the
    learner still sees the interface; only the implementation is removed.
    """
    spans = []
    for m in RE_JS_FUNCTION.finditer(source_text):
        open_idx = m.end() - 1  # the '{' captured at the end of the match
        if source_text[open_idx] != "{":
            continue
        close_idx = _find_matching_brace(source_text, open_idx)
        if close_idx < 0:
            continue
        spans.append((m.start(), open_idx, close_idx))

    if not spans:
        # No declared functions: fall through to the arrow/callback pass.
        return _stub_js_arrow_bodies(source_text)

    # Keep only the outermost spans. Nested functions are removed together with
    # their parent body; replacing an inner span would also shift the offsets
    # of every span after it and truncate the file.
    spans.sort()
    outer = []
    for start, open_idx, close_idx in spans:
        if outer and close_idx <= outer[-1][2]:
            continue
        outer.append((start, open_idx, close_idx))
    spans = outer

    # Replace from the end so earlier offsets stay valid.
    result = source_text
    for start, open_idx, close_idx in reversed(spans):
        indent = _js_indent_of_line(source_text, start)
        body_indent = indent + "  "
        new_body = (
            "\n"
            + body_indent + "// TODO: implement\n"
            + body_indent + 'throw new Error("Not implemented");\n'
            + indent
        )
        result = result[: open_idx + 1] + new_body + result[close_idx:]
    return _stub_js_arrow_bodies(result)


def _generate_js_test_skeleton(source_text: str, source_file: str) -> str:
    """Generate a JS/TS test skeleton (Jest/Vitest style) for source_file."""
    stem = Path(source_file).stem
    names = re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", source_text)
    names += re.findall(
        r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>",
        source_text,
    )
    # De-duplicate while preserving order.
    seen = set()
    fn_names = []
    for n in names:
        if n not in seen:
            seen.add(n)
            fn_names.append(n)

    lines = [
        f"// Tests for {source_file}",
        "// TODO: fill in the test bodies",
        "",
        f'describe("{stem}", () => {{',
    ]
    if fn_names:
        for fn in fn_names[:5]:
            lines += [
                f'  test("{fn} ...", () => {{',
                f"    // TODO: test {fn}",
                "    expect(true).toBe(false); // replace with a real assertion",
                "  });",
                "",
            ]
    else:
        lines += [
            '  test("placeholder", () => {',
            "    // TODO: add tests",
            "    expect(true).toBe(false); // replace with a real assertion",
            "  });",
            "",
        ]
    lines += ["});", ""]
    return "\n".join(lines)


def _stub_source(source_text: str, suffix: str) -> str:
    """Choose the correct body-stubber for the file type."""
    if suffix.lower() in JS_EXTS:
        return _stub_js_bodies(source_text)
    return _stub_function_body(source_text)


def _test_skeleton_for(source_text: str, source_file: str, suffix: str) -> str:
    """Choose the correct test-skeleton generator for the file type."""
    if suffix.lower() in JS_EXTS:
        return _generate_js_test_skeleton(source_text, source_file)
    return _generate_test_skeleton(source_text, source_file)


def _render_explainer(feature: str, entry_name: str, challenge_type: str,
                      difficulty: str, source_file: str, objective: str,
                      checks: list, hint_count: int) -> str:
    """Write the teaching half of a challenge.

    A problem plus a hidden solution teaches almost nothing: the learner needs
    to know what to notice, what 'done' means, and how the work will be judged
    before they start. This file carries that, and never the implementation.
    """
    kind = {
        "function_reconstruction": "rebuild a behaviour from its interface",
        "bug_fix": "find and fix a defect without rewriting the module",
        "test_writing": "pin behaviour down with tests that would catch a regression",
    }.get(challenge_type, challenge_type)

    lines = [
        "# Challenge: %s" % entry_name,
        "",
        "**Type:** %s (%s)  " % (challenge_type.replace("_", " "), difficulty),
        "**Skill this trains:** %s  " % kind,
        "**Source:** `%s`" % source_file,
        "",
        "## Objective",
        "",
        objective,
        "",
        "## Before you start",
        "",
        "1. Read the starter file in `workspace/` end to end. Note the imports and",
        "   the signatures; those are the contract you have to honour.",
        "2. Write down, in one sentence, what the module is responsible for. If you",
        "   cannot, re-read the graph entry for `%s` first." % feature,
        "3. Do not open the solution. It is not in the workspace, and you lose the",
        "   exercise the moment you read it.",
        "",
        "## Definition of done",
        "",
        "Every check below must pass:",
        "",
    ]
    for check in checks:
        lines.append("- **%s** — %s" % (check.get("id", "check"), check.get("description", "")))

    lines += [
        "",
        "## How you will be judged",
        "",
        "Passing checks is necessary, not sufficient. A defense answer about this",
        "module is scored on:",
        "",
        "- what it is responsible for, stated without naming a library;",
        "- the edge cases the original handles, and which ones it does not;",
        "- why this shape (module boundaries, seams) rather than the obvious one;",
        "- what would break if it were deleted.",
        "",
        "## Hints",
        "",
        "%d hint(s) are available in the manifest. Ask for one at a time; a hint"
        % hint_count,
        "counts as an attempt.",
        "",
    ]
    return "\n".join(lines)


def _build_checks(file_name: str, suffix: str) -> list:
    """Build a syntax check appropriate for the starter file type."""
    if suffix.lower() == ".py":
        return [{
            "id": "check-syntax",
            "description": "Verify the file has no Python syntax errors.",
            "command": ["python3", "-c",
                        f"import ast, sys; ast.parse(open(r'{file_name}', encoding='utf-8').read()); sys.exit(0)"],
            "expected_exit_code": 0,
            "timeout_seconds": 10,
        }]
    if suffix.lower() in {".js", ".mjs", ".cjs"}:
        return [{
            "id": "check-syntax",
            "description": "Verify the file has no JavaScript syntax errors (node --check).",
            "command": ["node", "--check", file_name],
            "expected_exit_code": 0,
            "timeout_seconds": 10,
        }]
    # JSX/TSX/TS cannot be checked by `node --check` without a toolchain.
    # Fall back to a structural check: the file must exist and be non-empty.
    return [{
        "id": "check-file-present",
        "description": "Verify the starter file exists and is not empty.",
        "command": ["python3", "-c",
                    f"import sys; sys.exit(0 if open(r'{file_name}', encoding='utf-8').read().strip() else 1)"],
        "expected_exit_code": 0,
        "timeout_seconds": 10,
    }]


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

    # Never fabricate a challenge for a feature that is not in the graph: the
    # old fallback produced a Python stub named after a JavaScript path (for
    # example `def server/index.js()`), which cannot be solved or checked.
    if entry is None:
        available = []
        for _section, candidate in _iter_entries(graph):
            name = str(candidate.get("name", "")).strip()
            if name and name not in available:
                available.append(name)
        preview = ", ".join(available[:12]) or "(none found)"
        sys.exit(
            f"Error: feature '{feature}' was not found in the project graph.\n"
            f"Available features include: {preview}\n"
            "Pick one of these names (a substring is enough), or add the feature "
            "to the graph during the Phase 4 verification loop."
        )

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
    # The evidence file is where the entry was *detected*; for frameworks that
    # declare a route in one file and implement it in another, relocate to the
    # file that actually defines the handler.
    if source_file:
        relocated = locate_handler(repo_root, entry.get("name", feature) if entry else feature,
                                   source_file)
        if relocated and relocated != source_file:
            source_file = relocated
            source_refs = [{
                "file": relocated,
                "lines": [1, 1],
                "description": entry.get("name", feature) if entry else feature,
            }]

    # Fallback: create a stub source file (only when the graph entry has no file).
    if not source_file:
        source_file = f"{_safe_ident(feature)}.py"
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
        original_text = f"# Stub for {source_file}\n\ndef {_safe_ident(entry_name)}():\n    pass\n"

    if challenge_type == "function_reconstruction":
        starter_content = _stub_source(original_text, source_suffix)
    elif challenge_type == "bug_fix":
        starter_content = _introduce_bug(original_text)
    else:  # test_writing
        starter_content = _test_skeleton_for(original_text, source_file, source_suffix)
        if source_suffix.lower() in JS_EXTS:
            starter_file_name = f"{source_stem}.test{source_suffix}"
        else:
            starter_file_name = f"test_{source_stem}{source_suffix}"

    # Never ship a starter that is byte-identical to the source: that is the
    # answer, not the exercise.
    if challenge_type in ("function_reconstruction", "bug_fix"):
        if starter_content.strip() == original_text.strip():
            sys.exit(
                f"Error: cannot build a '{challenge_type}' challenge from '{source_file}'.\n"
                "The generated starter would be identical to the original source, so it "
                "would leak the answer.\n"
                "Pick a file that contains function bodies (declarations, exported "
                "functions, or arrow callbacks), or choose a different --feature."
            )

    starter_file_path = starter_dir / starter_file_name
    starter_file_path.write_text(starter_content, encoding="utf-8")

    # Reference solution: kept beside the starter, never copied into the
    # workspace, and revealed by run_checks.py only once every check passes.
    # Hiding it from the workspace is what stops the answer being readable
    # while the exercise is open.
    solution_dir = challenge_dir / "solution"
    solution_dir.mkdir(parents=True, exist_ok=True)
    solution_name = str(Path(source_file).name) if source_file else starter_file_name
    solution_path = solution_dir / solution_name
    solution_path.write_text(original_text, encoding="utf-8")

    # Build workspace section
    workspace = {
        "allowed_files": [starter_file_name],
        "starter_file": starter_file_name,
    }

    # Build checks appropriate for the starter file type (Python AST,
    # `node --check`, or a structural check for JSX/TSX).
    checks = _build_checks(starter_file_name, source_suffix)

    # Explainer: the teaching half of the exercise (objective, what to read
    # first, definition of done, how the work is judged). A problem plus a
    # hidden solution teaches far less than one that says what to notice.
    explainer_path = challenge_dir / "explainer.md"
    explainer_path.write_text(
        _render_explainer(
            feature=feature,
            entry_name=entry_name,
            challenge_type=challenge_type,
            difficulty=difficulty,
            source_file=source_file,
            objective=objective,
            checks=checks,
            hint_count=len(hints),
        ),
        encoding="utf-8",
    )

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
        "explainer": "explainer.md",
        "solution_file": "solution/%s" % solution_name,
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
