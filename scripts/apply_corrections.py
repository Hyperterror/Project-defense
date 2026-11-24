#!/usr/bin/env python3
"""
apply_corrections.py -- Applies .project-defense/corrections.json to the graph.

Phase 4 is where a human corrects the machine's understanding. Those answers used
to be written to `corrections.json` and read by nothing: `build_graph.py` rebuilt
the graph from code facts on every run, so a confirmed route, a corrected auth
strategy or an answered uncertainty existed only in a file nobody opened.

This module is the missing link. `build_graph.py` calls it on every rebuild, so a
correction survives into the graph, the question bank and the readiness report.

Entry ids are the graph's own coordinates, so nothing has to be invented:

  route:GET /api/posts          a route in backend.routes
  model:Post                    a model in data.models
  component:Header              a component in frontend.components
  auth:strategy                 the auth strategy (needs a `value`)
  project:stack                 the stack list (needs a `value`)
  uncertainty:2                 the second entry in `uncertainties` (1-based)

Decisions map to the graph's status vocabulary:

  confirmed -> evidence.status = "user-provided", note appended to the excerpt
  corrected -> same, plus the entry's `value` replaces the detected content
  unknown   -> evidence.status = "UNVERIFIED"

An id that matches nothing is reported, never silently dropped: a typo would
otherwise look like a correction that was applied.

Stdlib only, Python 3.8+.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VALID_DECISIONS = {"confirmed", "corrected", "unknown"}

# Sections a correction id may address, with the shape of the selector.
ID_PATTERNS = {
    "route": re.compile(r"^route:(GET|POST|PUT|PATCH|DELETE|ANY) (/\S*)$", re.IGNORECASE),
    "model": re.compile(r"^model:(\w+)$"),
    "component": re.compile(r"^component:(\w+)$"),
    "auth": re.compile(r"^auth:strategy$"),
    "project": re.compile(r"^project:stack$"),
    "uncertainty": re.compile(r"^uncertainty:(\d+)$"),
}

VALID_ID_HELP = (
    "route:<METHOD> <path>   e.g. route:GET /api/posts\n"
    "model:<Name>            e.g. model:Post\n"
    "component:<Name>        e.g. component:Header\n"
    "auth:strategy           with --value JWT|session|cookie|OAuth|API key|none\n"
    "project:stack           with --value \"Django,PostgreSQL\"\n"
    "uncertainty:<n>         1-based index into graph.uncertainties"
)


def validate_id(entry_id: str) -> Tuple[str, str]:
    """Split a correction id into (section, selector) or exit with the grammar."""
    for section, pattern in ID_PATTERNS.items():
        match = pattern.match(entry_id)
        if match:
            selector = match.group(1) if match.groups() else ""
            if section == "route":
                selector = f"{match.group(1).upper()} {match.group(2)}"
            return section, selector
    sys.exit(
        f"Error: '{entry_id}' is not a correction id this graph understands.\n"
        f"Use one of:\n{VALID_ID_HELP}"
    )


def _note_text(entry: Dict[str, Any]) -> str:
    note = (entry.get("note") or "").strip()
    decision = entry.get("decision", "")
    label = {"confirmed": "confirmed by user", "corrected": "corrected by user",
             "unknown": "user does not know"}.get(decision, decision)
    return f"[{label}{': ' + note if note else ''}]"


def _mark(evidence: Dict[str, Any], entry: Dict[str, Any]) -> None:
    """Stamp a graph evidence block with the human's decision."""
    decision = entry.get("decision")
    if decision == "unknown":
        evidence["status"] = "UNVERIFIED"
        return
    evidence["status"] = "user-provided"
    excerpt = (evidence.get("excerpt") or "").strip()
    addition = _note_text(entry)
    evidence["excerpt"] = (excerpt + " " + addition).strip()[:400]


def _find_route(routes: List[Dict[str, Any]], selector: str) -> Optional[Dict[str, Any]]:
    method, _, path = selector.partition(" ")
    path = path.strip()
    for route in routes:
        if route.get("method", "").upper() != method.upper():
            continue
        if route.get("path", "").rstrip("/") == path.rstrip("/"):
            return route
    return None


def apply_corrections(graph: Dict[str, Any],
                      corrections: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Apply every correction to `graph` in place and report what happened.

    Returns {"applied": [ids], "unmatched": [ids]}. Unmatched ids are the ones
    that referenced a route, model, component or uncertainty that no longer
    exists -- usually because the code changed. They are reported so the agent can
    re-ask instead of pretending the correction landed.
    """
    applied: List[str] = []
    unmatched: List[str] = []

    routes = graph.get("backend", {}).get("routes", [])
    models = graph.get("data", {}).get("models", [])
    components = graph.get("frontend", {}).get("components", [])
    uncertainties = graph.get("uncertainties", [])

    for entry_id in sorted(corrections):
        entry = corrections[entry_id] or {}
        if entry.get("decision") not in VALID_DECISIONS:
            continue
        section, selector = validate_id(entry_id)

        target: Optional[Dict[str, Any]] = None
        if section == "route":
            target = _find_route(routes, selector)
        elif section == "model":
            target = next((m for m in models if m.get("name") == selector), None)
        elif section == "component":
            target = next((c for c in components if c.get("name") == selector), None)
        elif section == "uncertainty":
            index = int(selector) - 1
            if 0 <= index < len(uncertainties):
                target = uncertainties[index]
        elif section == "auth":
            value = entry.get("value")
            if isinstance(value, str) and value:
                graph.setdefault("auth", {})["strategy"] = value
                applied.append(entry_id)
            else:
                unmatched.append(entry_id)
            continue
        elif section == "project":
            value = entry.get("value")
            if isinstance(value, list) and value:
                graph.setdefault("project", {})["stack"] = [str(v) for v in value]
                applied.append(entry_id)
            elif isinstance(value, str) and value:
                graph.setdefault("project", {})["stack"] = [
                    part.strip() for part in value.split(",") if part.strip()
                ]
                applied.append(entry_id)
            else:
                unmatched.append(entry_id)
            continue

        if target is None:
            unmatched.append(entry_id)
            continue

        evidence = target.get("evidence")
        if isinstance(evidence, dict):
            _mark(evidence, entry)
        elif section == "uncertainty":
            # Uncertainties may carry the human's answer instead of evidence.
            answer = (entry.get("note") or "").strip()
            if entry.get("decision") == "confirmed":
                target["resolved"] = True
            if answer:
                target["user_answer"] = answer
            if entry.get("value"):
                target["value"] = entry["value"]

        # A corrected entry may carry the right answer outright.
        value = entry.get("value")
        if entry.get("decision") == "corrected" and value is not None:
            if section == "route" and isinstance(value, dict):
                for key in ("path", "handler", "method"):
                    if key in value:
                        target[key] = value[key]
            elif section == "model" and isinstance(value, dict):
                for key in ("name", "fields"):
                    if key in value:
                        target[key] = value[key]
            elif section in ("model", "component", "uncertainty") and isinstance(value, str):
                target["value"] = value

        applied.append(entry_id)

    return {"applied": applied, "unmatched": unmatched}


def load_corrections_file(repo_root: Path) -> Dict[str, Dict[str, Any]]:
    """Read corrections.json; a corrupt file stops the rebuild with a fix-it hint."""
    path = repo_root / ".project-defense" / "corrections.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(
            f"Error: {path} is not valid JSON, so the graph cannot apply it.\n"
            f"Fix or delete the file and rebuild.\nDetails: {exc}"
        )
    if not isinstance(data, dict):
        sys.exit(f"Error: {path} must be a JSON object of entry-id -> decision.")
    return data


def apply_from_disk(repo_root: Path, graph: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience wrapper used by build_graph.py."""
    corrections = load_corrections_file(repo_root)
    if not corrections:
        return {"applied": [], "unmatched": []}
    return apply_corrections(graph, corrections)
