#!/usr/bin/env python3
"""
check_graph_freshness.py -- Detect whether project-graph.json is stale.

A knowledge graph silently goes out of date the moment the repository moves
on. Downstream phases trust the graph, so they need a cheap way to check it
before they quote it in documentation or ask interview questions from it.

Usage:
  python3 check_graph_freshness.py <repo-root>
  python3 check_graph_freshness.py <repo-root> --json

Output (stdout, always JSON):
  {
    "graph_path": "...",
    "analyzed_at": "2026-10-19T10:00:00+00:00",
    "graph_head": "<commit>",
    "current_head": "<commit>",
    "commits_behind": 3,
    "fresh": false,
    "reason": "graph was built at <sha>; HEAD is now <sha>"
  }

Exit codes:
  0  fresh (or freshness cannot be determined)
  1  stale
  2  graph missing or unreadable

Freshness is measured two ways: against git HEAD when the repository has git,
otherwise against a content fingerprint of the source files recorded at
analysis time.

Stdlib only, Python 3.8+.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from path_filters import load_ignore_patterns, walk_files
    from detect_code_facts import is_source_file
except ImportError:  # pragma: no cover - keeps the script usable standalone
    load_ignore_patterns = None
    walk_files = None
    is_source_file = None


def content_fingerprint(repo_root: Path) -> str:
    """Hash the project's source files (path, size, mtime) into one digest.

    This is the fallback for repositories with no git history: it cannot say
    *which* commit moved, only that the files did. Size and mtime are enough to
    catch an edit without reading every file's contents.
    """
    if walk_files is None or is_source_file is None:
        return ""
    root = Path(repo_root).resolve()
    digest = hashlib.sha256()
    try:
        for path in walk_files(root, load_ignore_patterns(root)):
            if not is_source_file(path):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            digest.update(("%s:%d:%d\n" % (rel, stat.st_size, stat.st_mtime_ns)).encode())
    except Exception:
        return ""
    return digest.hexdigest()


def _git(repo_root: Path, *args: str) -> str:
    """Run a git command and return stdout, or '' on any failure."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root)] + list(args),
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def check_freshness(repo_root: Path) -> dict:
    """Return the freshness report dict for repo_root."""
    graph_path = Path(repo_root).resolve() / ".project-defense" / "project-graph.json"

    report = {
        "graph_path": str(graph_path),
        "analyzed_at": "",
        "graph_head": "",
        "current_head": "",
        "commits_behind": 0,
        "fresh": True,
        "reason": "",
        "checked_by": "git",
    }

    if not graph_path.exists():
        report["fresh"] = False
        report["reason"] = "project-graph.json not found; run the analysis phases first"
        return report

    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report["fresh"] = False
        report["reason"] = "project-graph.json is not valid JSON: {}".format(exc)
        return report

    report["analyzed_at"] = graph.get("analyzed_at", "")
    report["graph_head"] = graph.get("git_head", "")
    report["current_head"] = _git(repo_root, "rev-parse", "HEAD")

    if not report["current_head"]:
        # No git history: fall back to a content fingerprint when the graph has
        # one (repos built by build_graph.py after this change do).
        recorded = graph.get("content_fingerprint", "")
        current = content_fingerprint(repo_root)
        report["checked_by"] = "content_fingerprint"
        if recorded and current:
            if recorded == current:
                report["fresh"] = True
                report["reason"] = "source files unchanged since analysis"
            else:
                report["fresh"] = False
                report["reason"] = (
                    "source files changed since analysis (no git history to say "
                    "which ones); re-run the analysis phases"
                )
            return report
        report["fresh"] = True
        report["reason"] = (
            "not a git repository and the graph has no content_fingerprint; "
            "freshness cannot be verified"
        )
        return report

    if not report["graph_head"]:
        report["fresh"] = False
        report["reason"] = (
            "the graph has no git_head (built by an older version); re-run "
            "scripts/build_graph.py to record one"
        )
        return report

    if report["graph_head"] == report["current_head"]:
        report["fresh"] = True
        report["reason"] = "graph matches HEAD"
        return report

    behind = _git(repo_root, "rev-list", "--count",
                  "{}..HEAD".format(report["graph_head"]))
    if behind.isdigit():
        report["commits_behind"] = int(behind)
    report["fresh"] = False
    report["reason"] = (
        "graph was built at {}; HEAD is now {}{}".format(
            report["graph_head"][:12],
            report["current_head"][:12],
            " ({} commit(s) behind)".format(report["commits_behind"])
            if report["commits_behind"] else "",
        )
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check whether .project-defense/project-graph.json matches git HEAD."
    )
    parser.add_argument("repo_root", help="Path to the analyzed repository.")
    parser.add_argument("--json", action="store_true",
                        help="Accepted for compatibility; output is always JSON.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists():
        sys.exit("Error: repository path '{}' does not exist.".format(repo_root))

    report = check_freshness(repo_root)
    print(json.dumps(report, indent=2))

    if not Path(report["graph_path"]).exists():
        sys.exit(2)
    sys.exit(0 if report["fresh"] else 1)


if __name__ == "__main__":
    main()
