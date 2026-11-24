#!/usr/bin/env python3
"""
path_filters.py -- Shared path filtering for the project-defense scanner.

Both scan_repository.py and detect_code_facts.py walk a repository. Without a
shared filter they disagree: the detector skipped node_modules while the
scanner did not, so third-party package.json files polluted framework
detection and vendored source leaked into env-var extraction.

This module provides:
  - the canonical noise-directory skip list
  - `.project-defenseignore` support (gitignore-ish globs, `!` negation)
  - walk_files() -- a single pruned directory walk used by both scripts

Stdlib only, compatible with Python 3.8+.
"""

import fnmatch
import os
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence

# Directory names that never contain project code worth analyzing.
# Keep this list in sync with the documentation in README.md.
SKIP_DIR_NAMES = {
    "node_modules",
    "__pycache__",
    ".git",
    ".svn",
    ".hg",
    "dist",
    "build",
    "out",
    "target",
    ".next",
    ".nuxt",
    ".turbo",
    ".svelte-kit",
    "venv",
    ".venv",
    "env",
    ".env",
    "vendor",
    "Pods",
    "DerivedData",
    "coverage",
    ".nyc_output",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".project-defense",
    "site-packages",
}

# Dot-directories that hold real configuration and should still be walked.
DOT_DIRS_TO_KEEP = {".github", ".gitlab", ".circleci", ".vscode", ".devcontainer"}

IGNORE_FILENAME = ".project-defenseignore"


# ----------------------------------------------------------------------
# Ignore rules
# ----------------------------------------------------------------------


def load_ignore_patterns(root: Path, filename: str = IGNORE_FILENAME) -> List[str]:
    """Read ignore patterns from <root>/<filename>.

    Format follows the useful subset of .gitignore:
      - blank lines and lines starting with '#' are ignored
      - a trailing '/' matches a directory and everything under it
      - '!' negates an earlier match (last matching rule wins)
      - '*' and '?' are shell wildcards; '**/' also matches at any depth

    Returns [] when the file does not exist.
    """
    path = Path(root) / filename
    if not path.is_file():
        return []
    patterns: List[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def _glob_match(rel_posix: str, pattern: str) -> bool:
    """Match one ignore pattern against a repo-relative POSIX path."""
    pat = pattern.lstrip("./")
    if pat.endswith("/"):
        prefix = pat.rstrip("/")
        return rel_posix == prefix or rel_posix.startswith(prefix + "/")
    if pat.startswith("**/"):
        pat = pat[3:]
        if fnmatch.fnmatchcase(rel_posix, pat):
            return True
        # also match at any depth
        return fnmatch.fnmatchcase(rel_posix, "*/" + pat)
    if "/" in pat:
        return fnmatch.fnmatchcase(rel_posix, pat)
    # No slash: match the basename or any path segment, like gitignore.
    return (
        fnmatch.fnmatchcase(rel_posix.rsplit("/", 1)[-1], pat)
        or fnmatch.fnmatchcase(rel_posix, "*/" + pat)
    )


def is_ignored(rel_path: Path, patterns: Sequence[str]) -> bool:
    """Return True when rel_path is excluded by the ignore patterns."""
    if not patterns:
        return False
    rel = Path(rel_path).as_posix()
    ignored = False
    for pattern in patterns:
        negated = pattern.startswith("!")
        pat = pattern[1:] if negated else pattern
        if not pat:
            continue
        if _glob_match(rel, pat):
            ignored = not negated
    return ignored


# ----------------------------------------------------------------------
# Walking
# ----------------------------------------------------------------------


def is_noise_dir(name: str) -> bool:
    """Return True when a directory name should be pruned from the walk."""
    if name in SKIP_DIR_NAMES:
        return True
    if name.startswith(".") and name not in DOT_DIRS_TO_KEEP:
        return True
    return False


def walk_files(
    root: Path,
    ignore_patterns: Optional[Sequence[str]] = None,
    keep_dot_dirs: bool = True,
) -> Iterator[Path]:
    """Yield every non-ignored file under root, pruning noise directories.

    Deterministic: directory entries are sorted so repeated runs produce the
    same order on every platform.
    """
    root = Path(root).resolve()
    patterns: List[str] = list(ignore_patterns or [])
    dirs_to_keep = DOT_DIRS_TO_KEEP if keep_dot_dirs else set()

    for dirpath, dirnames, filenames in os.walk(str(root)):
        current = Path(dirpath)
        pruned = []
        for d in sorted(dirnames):
            if d in SKIP_DIR_NAMES:
                continue
            if d.startswith(".") and d not in dirs_to_keep:
                continue
            rel_dir = (current / d).relative_to(root)
            if patterns and is_ignored(rel_dir, patterns):
                continue
            pruned.append(d)
        dirnames[:] = pruned

        for name in sorted(filenames):
            full = current / name
            try:
                rel = full.relative_to(root)
            except ValueError:
                continue
            if patterns and is_ignored(rel, patterns):
                continue
            yield full


def walk_source_files(
    root: Path,
    extensions: Iterable[str],
    ignore_patterns: Optional[Sequence[str]] = None,
) -> List[Path]:
    """Yield only files whose suffix is in extensions (case-insensitive)."""
    exts = {e.lower() for e in extensions}
    return [
        p for p in walk_files(root, ignore_patterns)
        if p.suffix.lower() in exts and p.is_file()
    ]
