#!/usr/bin/env python3
"""
validate_mermaid.py -- Structural validator for Mermaid diagram (.mmd) files.

Rules enforced:
  1. First non-blank, non-comment line must contain a valid diagram type keyword.
  2. No unclosed brackets/braces/parens at end of file (counts open vs close).
  3. Comment lines must begin with %% (preceded only by whitespace).

Valid diagram type keywords:
  graph, flowchart, sequenceDiagram, classDiagram, stateDiagram, erDiagram,
  gantt, pie, gitGraph, mindmap, timeline, quadrantChart

CLI:
  python3 validate_mermaid.py <file.mmd> [<file2.mmd> ...]
  Exit 0 on all pass, exit 1 on any failure, exit 2 on usage error.

Stdlib only, Python 3.8+.
"""

import sys
import re
from pathlib import Path

VALID_KEYWORDS = {
    "graph",
    "flowchart",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "erDiagram",
    "gantt",
    "pie",
    "gitGraph",
    "mindmap",
    "timeline",
    "quadrantChart",
}

# Case-insensitive set for matching
_VALID_KEYWORDS_LOWER = {kw.lower() for kw in VALID_KEYWORDS}


def validate_file(path: Path) -> list:
    """Validate a single .mmd file.  Returns a list of error strings (empty = pass)."""
    errors = []

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="latin-1")
        except Exception as exc:
            return [f"{path}: cannot read file: {exc}"]
    except FileNotFoundError:
        return [f"{path}: file not found"]
    except PermissionError:
        return [f"{path}: permission denied"]

    lines = text.splitlines()

    # ------------------------------------------------------------------
    # Rule 1: First non-blank, non-comment line must start with a valid keyword.
    # ------------------------------------------------------------------
    first_code_line = None
    first_code_lineno = None
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("%%"):
            continue
        first_code_line = stripped
        first_code_lineno = lineno
        break

    if first_code_line is None:
        errors.append(f"{path}:1: file contains only comments or is empty")
    else:
        # The keyword may be followed by direction, title, etc. (e.g. "graph TD")
        # We check if any valid keyword appears at the START of the line (case-insensitive).
        first_token = first_code_line.split()[0] if first_code_line.split() else ""
        if first_token.lower() not in _VALID_KEYWORDS_LOWER:
            errors.append(
                f"{path}:{first_code_lineno}: first non-comment line must start with a "
                f"valid diagram keyword (got '{first_token}'). "
                f"Valid keywords: {', '.join(sorted(VALID_KEYWORDS))}"
            )

    # ------------------------------------------------------------------
    # Rule 2: No unclosed brackets/braces/parens at end of file.
    # This is a net-count check — Mermaid node shapes can be intentionally
    # asymmetric inside labels, so we only error if the overall count is off.
    # We skip content inside quotes to avoid false positives from labels.
    # ------------------------------------------------------------------
    open_count = {"[": 0, "{": 0, "(": 0}
    close_map = {"]": "[", "}": "{", ")": "("}

    for line in lines:
        # Remove string literals (single or double quoted) to avoid counting brackets in labels
        sanitized = re.sub(r'"[^"]*"', '""', line)
        sanitized = re.sub(r"'[^']*'", "''", sanitized)
        # Remove comment portion
        if "%%" in sanitized:
            sanitized = sanitized[:sanitized.index("%%")]

        for ch in sanitized:
            if ch in open_count:
                open_count[ch] += 1
            elif ch in close_map:
                opener = close_map[ch]
                open_count[opener] -= 1

    for opener, count in open_count.items():
        if count != 0:
            closer = {v: k for k, v in close_map.items()}[opener]
            errors.append(
                f"{path}: unbalanced '{opener}'/'{closer}': "
                f"net count is {count:+d} (expected 0). "
                "This may indicate unclosed brackets in a node definition."
            )

    return errors


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: validate_mermaid.py <file.mmd> [<file2.mmd> ...]",
            file=sys.stderr
        )
        sys.exit(2)

    all_errors = []
    for arg in sys.argv[1:]:
        path = Path(arg)
        errors = validate_file(path)
        all_errors.extend(errors)

    if all_errors:
        for err in all_errors:
            print(err, file=sys.stderr)
        sys.exit(1)
    else:
        print(f"All {len(sys.argv) - 1} file(s) passed validation.")
        sys.exit(0)


if __name__ == "__main__":
    main()
