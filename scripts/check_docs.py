#!/usr/bin/env python3
"""
check_docs.py -- Integrity lint for the skill's own documentation and wiring.

A skill is only as good as its wiring: a script nobody is told to run, a
template nobody references, or a link that no longer resolves is dead weight
that the agent will silently skip. This script checks the repo the way a
linter checks code:

  1. SKILL.md has valid frontmatter with a non-empty `name` and `description`.
  2. Every relative markdown link in the repo resolves to a real file.
  3. Every `scripts/<file>` / `templates/<file>` / `rubrics/<file>` path named
     in the docs actually exists.
  4. Every script under scripts/ is mentioned by at least one document, so no
     script ships unreachable.
  5. Every rubric file is valid JSON and has a unique `id`.
  6. The score weights printed in `instructions/02-generate-docs.md` match
     `CATEGORY_WEIGHTS` in `scripts/score_report.py`, so the agent never quotes
     a weighting the scorer does not use.

Usage:
    python scripts/check_docs.py [repo_root]

Exit codes: 0 = clean, 1 = problems found (each problem is printed on its own
line as `<file>: <reason>`).

Stdlib only, Python 3.8+.
"""

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent

# Directories that are produced by running the skill, not documentation.
SKIP_DIRS = {".git", ".project-defense", "node_modules", "__pycache__"}

# A path mention inside backticks, e.g. `scripts/scan_repository.py`.
RE_PATH_MENTION = re.compile(
    r"^(scripts|templates|rubrics|instructions|tests)/[A-Za-z0-9._/-]+$"
)
# A markdown link target, e.g. [x](./docs/thing.md) or [x](templates/a.md)
RE_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _iter_docs(root: Path):
    """Yield every markdown file that belongs to the documentation."""
    for path in sorted(root.rglob("*.md")):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def check_frontmatter(root: Path, problems: list) -> None:
    skill_md = root / "SKILL.md"
    if not skill_md.exists():
        problems.append("SKILL.md: missing")
        return
    text = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\r?\n([\s\S]*?)\r?\n---", text)
    if not match:
        problems.append("SKILL.md: no frontmatter block")
        return
    fields = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    for key in ("name", "description"):
        if not fields.get(key):
            problems.append("SKILL.md: frontmatter is missing a non-empty `%s`" % key)
    name = fields.get("name", "")
    if name and not re.match(r"^[a-z0-9][a-z0-9-]*$", name):
        problems.append(
            "SKILL.md: `name` should be dash-case (got %r)" % name
        )


def check_links(root: Path, problems: list) -> None:
    for doc in _iter_docs(root):
        text = doc.read_text(encoding="utf-8")
        rel_doc = doc.relative_to(root).as_posix()
        for target in RE_MD_LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            clean = target.split("#", 1)[0].strip()
            if not clean:
                continue
            resolved = (doc.parent / clean).resolve()
            if not resolved.exists():
                problems.append("%s: broken link -> %s" % (rel_doc, target))


def check_path_mentions(root: Path, problems: list) -> None:
    """Every file path named in backticks must exist."""
    for doc in _iter_docs(root):
        text = doc.read_text(encoding="utf-8")
        rel_doc = doc.relative_to(root).as_posix()
        for token in re.findall(r"`([^`\n]+)`", text):
            token = token.strip()
            if not RE_PATH_MENTION.match(token):
                continue
            if not (root / token).exists():
                problems.append("%s: references missing path -> %s" % (rel_doc, token))


def check_script_reachability(root: Path, problems: list) -> None:
    """Every script must be named in at least one document."""
    scripts_dir = root / "scripts"
    if not scripts_dir.is_dir():
        return
    docs_text = "\n".join(
        doc.read_text(encoding="utf-8") for doc in _iter_docs(root)
    )
    for script in sorted(scripts_dir.glob("*.py")):
        if script.name in docs_text:
            continue
        problems.append(
            "scripts/%s: never mentioned in any document (dead wiring)" % script.name
        )


def check_rubrics(root: Path, problems: list) -> None:
    rubrics_dir = root / "rubrics"
    if not rubrics_dir.is_dir():
        return
    seen = {}
    for path in sorted(rubrics_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - report, do not crash
            problems.append("rubrics/%s: invalid JSON (%s)" % (path.name, exc))
            continue
        rubric_id = data.get("id")
        if not rubric_id:
            problems.append("rubrics/%s: missing `id`" % path.name)
            continue
        if rubric_id in seen:
            problems.append(
                "rubrics/%s: duplicate id %r (also in %s)"
                % (path.name, rubric_id, seen[rubric_id])
            )
        else:
            seen[rubric_id] = path.name


def check_score_weights(root: Path, problems: list) -> None:
    """The documented weights must be the weights the scorer actually applies."""
    doc = root / "instructions" / "02-generate-docs.md"
    if not doc.is_file():
        return
    sys.path.insert(0, str(SKILL_DIR / "scripts"))
    try:
        from score_report import CATEGORY_WEIGHTS
    except Exception as exc:  # noqa: BLE001 - report, do not crash
        problems.append("scripts/score_report.py: unreadable (%s)" % exc)
        return
    text = doc.read_text(encoding="utf-8")
    for category, weight in CATEGORY_WEIGHTS.items():
        expected = "%s: %d%%" % (category, round(weight * 100))
        if expected not in text:
            problems.append(
                "instructions/02-generate-docs.md: missing score weight %r "
                "(from score_report.CATEGORY_WEIGHTS)" % expected
            )


def check(root: Path) -> list:
    problems = []
    check_frontmatter(root, problems)
    check_links(root, problems)
    check_path_mentions(root, problems)
    check_script_reachability(root, problems)
    check_rubrics(root, problems)
    check_score_weights(root, problems)
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("repo_root", nargs="?", default=str(SKILL_DIR),
                        help="Skill repository root (defaults to this script's repo)")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    if not root.is_dir():
        sys.exit("Error: '%s' is not a directory." % root)

    problems = check(root)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        sys.exit(
            "\n%d documentation/wiring problem(s) found.\n"
            "Fix the paths, or delete what is no longer used." % len(problems)
        )
    print("Documentation and wiring are consistent.")


if __name__ == "__main__":
    main()
