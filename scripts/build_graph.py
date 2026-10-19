#!/usr/bin/env python3
"""
build_graph.py -- Build a project-graph.json from scan + code-facts.

Takes:
  - .project-defense/scan-facts.json  (from scan_repository.py)
  - .project-defense/code-facts.json  (from detect_code_facts.py)
  - package.json (read for project name and entry points)

Writes:
  - .project-defense/project-graph.json  (validated against templates/project-graph.schema.json)

The graph is what the rest of the workflow (docs, diagrams, learning path,
question bank, mock interview) consumes. It MUST conform to the schema.

The graph includes EVERY graph entry with status='code-verified' and
'evidence: { file, lines, excerpt, status }'. The agent then runs the
verification loop (Phase 4) to mark entries as 'user-provided' or
'UNVERIFIED' based on user input.

Stdlib only, Python 3.8+. No external dependencies.

Usage:
  python3 build_graph.py <repo-root>
  python3 build_graph.py <repo-root> --no-validate    # skip schema check
  python3 build_graph.py <repo-root> --pretty         # pretty-print (default)
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Local import — works whether the script is run from any cwd
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
try:
    from validate_graph import validate_value
except ImportError:
    validate_value = None  # type: ignore


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def make_evidence(file: str, lines: List[int], excerpt: str) -> Dict[str, Any]:
    """Build an evidence record. Status defaults to 'code-verified'."""
    return {
        "file": file,
        "lines": lines,
        "excerpt": excerpt[:200],  # schema cap
        "status": "code-verified",
    }


def name_from_path(path: str) -> str:
    """Turn 'src/components/TodoList.jsx' into 'TodoList'."""
    return Path(path).stem


# ----------------------------------------------------------------------
# Build each section
# ----------------------------------------------------------------------


def build_project(scan: Dict[str, Any], repo_root: Path) -> Dict[str, Any]:
    """Project metadata: name from package.json or directory name, entry points."""
    pkg_path = repo_root / "package.json"
    pkg = {}
    if pkg_path.exists():
        try:
            pkg = json.loads(pkg_path.read_text())
        except json.JSONDecodeError:
            pass
    name = pkg.get("name") or repo_root.name
    # Build a one-line purpose (the agent will refine this in Phase 4)
    description = pkg.get("description", f"Auto-detected project at {repo_root.name}")
    purpose = f"{description}. (Purpose is auto-filled; the agent must confirm or correct in Phase 4.)"

    # Stack from frameworks
    fw = scan.get("frameworks", {})
    stack = []
    stack.extend(fw.get("frontend", []))
    stack.extend(fw.get("backend", []))
    stack.extend(fw.get("database", []))
    if not stack:
        # Fall back to language detection
        langs = list(scan.get("languages", {}).keys())
        stack = langs[:3]

    # Entry points: prefer package.json's "main" or the detected list
    entry_points = []
    entry_files = scan.get("entry_points", []) or []
    if isinstance(pkg.get("main"), str):
        entry_points.append({"file": pkg["main"], "type": "backend"})
    for ep in entry_files[:5]:
        ep_type = "backend" if "server" in ep or "app" in Path(ep).stem else "frontend"
        entry_points.append({"file": ep, "type": ep_type})

    return {
        "name": name,
        "purpose": purpose,
        "stack": stack,
        "entry_points": entry_points,
    }


def build_frontend(code: Dict[str, Any]) -> Dict[str, Any]:
    """Frontend: components, hooks as components, api_calls."""
    react = code.get("react", {})

    # Components
    components = []
    for c in react.get("components", []):
        components.append({
            "name": c["name"],
            "details": c.get("details", {"type": "component"}),
            "evidence": c["evidence"],
        })
    # Hooks go in their own bucket per schema (state_management)
    hooks = []
    for h in react.get("hooks", []):
        hooks.append({
            "name": h["name"],
            "details": h.get("details", {"type": "hook"}),
            "evidence": h["evidence"],
        })

    # API calls
    api_calls = []
    for a in code.get("api_calls", []):
        d = a.get("details", {})
        api_calls.append({
            "name": a["name"],
            "details": d,
            "evidence": a["evidence"],
        })

    return {
        "pages": [],  # Not auto-detected; agent refines in Phase 4
        "components": components,
        "state_management": hooks,
        "api_calls": api_calls,
    }


def build_backend(code: Dict[str, Any]) -> Dict[str, Any]:
    """Backend: routes, middleware, controllers, services."""
    express = code.get("express", {})

    routes = []
    for r in express.get("routes", []):
        handler = r.get("handler")
        # The schema requires handler to be a string. When the detector could
        # not extract a named handler (e.g., for inline arrow functions), we
        # fall back to the route file basename so the graph validates. The
        # agent refines this in Phase 4 to a real function/closure name.
        if not handler:
            handler = Path(r["evidence"]["file"]).stem
        routes.append({
            "method": r["method"],
            "path": r["path"],
            "handler": handler,
            "evidence": r["evidence"],
        })

    middleware = []
    for m in express.get("middleware", []):
        middleware.append({
            "name": m["name"],
            "details": {"path_prefix": m.get("path_prefix")},
            "evidence": m["evidence"],
        })

    return {
        "routes": routes,
        "middleware": middleware,
        "controllers": [],  # Not auto-detected; agent refines in Phase 4
        "services": [],     # Not auto-detected; agent refines in Phase 4
    }


def build_data(code: Dict[str, Any]) -> Dict[str, Any]:
    """Data layer: Mongoose models, Django models, SQLAlchemy models, relationships (inferred)."""
    models = []
    relationships = []

    # Mongoose models (v1 supported stack)
    for m in code.get("mongoose", {}).get("models", []):
        models.append({
            "name": m["name"],
            "fields": m.get("fields", []),
            "evidence": m["evidence"],
        })

    # Python ORM models (Django, SQLAlchemy -- experimental stacks)
    for m in code.get("python_orm", {}).get("models", []):
        models.append({
            "name": m["name"],
            "fields": m.get("fields", []),
            "evidence": m["evidence"],
        })

    # Heuristic relationship inference: look for ObjectId refs across models
    # by scanning source for 'ref: "ModelName"'. The detector doesn't do this yet,
    # so we leave relationships empty for the agent to fill in.
    return {
        "models": models,
        "relationships": relationships,
        "migrations": [],  # MongoDB typically has no migrations; Mongoose init counts.
    }


def build_auth(code: Dict[str, Any], backend_routes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Auth strategy + protected routes, inferred from code signals."""
    auth_signals = code.get("auth", {})
    jwt_count = len(auth_signals.get("jwt_verify", []))
    bcrypt_count = len(auth_signals.get("bcrypt_usage", []))

    if jwt_count > 0:
        strategy = "JWT"
        # Token handling hint: where the JWT is decoded
        if auth_signals["jwt_verify"]:
            sample = auth_signals["jwt_verify"][0]
            token_handling = (
                f"JWT verified in {sample['file']} -- typically passed in the "
                f"Authorization: Bearer header. Confirm exact mechanism with user."
            )
        else:
            token_handling = "JWT-based auth detected. Confirm storage (cookie, localStorage, etc.) with user."
    elif bcrypt_count > 0:
        strategy = "session"
        token_handling = "Password hashing detected (bcrypt); session-based auth likely. Confirm with user."
    else:
        strategy = "other"
        token_handling = "Auth strategy not auto-detected. Mark UNVERIFIED and ask user."

    # Protected routes: routes whose mount path has an auth-MIDDLEWARE (not auth-router) mount.
    # The signal: a mount with path_prefix AND name matching /auth.*(middleware|MW|guard|verify)/i.
    # We deliberately EXCLUDE mounts whose name ends in "Routes" (those are sub-routers,
    # not protection middleware).
    middleware_with_prefix = [
        m for m in code.get("express", {}).get("middleware", [])
        if m.get("path_prefix") and not m["name"].endswith("Routes")
        and re.search(r"auth.*(middleware|mw|guard|verify|check)", m["name"], re.IGNORECASE)
    ]
    protected_prefixes = {m["path_prefix"] for m in middleware_with_prefix}
    protected_routes = []
    for r in backend_routes:
        for prefix in protected_prefixes:
            if r["path"].startswith(prefix):
                protected_routes.append({
                    "name": f"{r['method']} {r['path']}",
                    "details": {"method": r["method"], "path": r["path"]},
                    "evidence": r["evidence"],
                })
                break

    return {
        "strategy": strategy,
        "token_handling": token_handling,
        "protected_routes": protected_routes,
    }


def build_user_flows(backend_routes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """User flows are NOT auto-detected; the agent builds these in Phase 4
    by reading the routes and inferring journeys. We seed an empty list and
    the agent populates it from the verification loop output.
    """
    return []


def build_data_flows(api_calls: List[Dict[str, Any]], backend_routes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Data flows: NOT auto-detected end-to-end. The agent assembles these from
    matched frontend API calls + backend routes. We leave the list empty;
    the agent fills it in during the verification loop.
    """
    return []


def build_risks(code: Dict[str, Any], scan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Risks: things the code reveals as risky. Conservative -- only flag if signal is strong."""
    risks = []
    # No tests?
    if not scan.get("test_dirs"):
        # Find a config file or repo root as evidence
        readme = scan.get("readme_path") or "package.json"
        risks.append({
            "description": "No test directory detected. The project has no automated tests.",
            "severity": "high",
            "evidence": {
                "file": readme,
                "lines": [1, 1],
                "excerpt": "no test/ or __tests__/ directory found",
                "status": "code-verified",
            },
            "mitigation": "Add at least a smoke test for the critical-path endpoints (e.g., auth + one CRUD).",
        })
    return risks


def build_uncertainties(code: Dict[str, Any], scan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Uncertainties: things the code cannot tell us. These are questions for Phase 4."""
    uncertainties = []
    # JWT secret source?
    if any("JWT_SECRET" in v for v in scan.get("env_vars", [])):
        uncertainties.append({
            "question": "Where is the JWT secret stored in production? .env file? Secret manager?",
            "context": "Code references process.env.JWT_SECRET but the deployment mechanism is not visible in source.",
            "evidence": {
                "file": "scan-facts.json",
                "lines": [1, 1],
                "excerpt": "env var JWT_SECRET detected",
                "status": "code-verified",
            },
            "impact_if_wrong": "Cannot recommend a secure secret-rotation strategy; cannot warn about leaked-secret risk.",
        })
    # Mongoose connection: env var or hardcoded?
    if any("MONGODB_URI" in v or "MONGO_URL" in v for v in scan.get("env_vars", [])):
        uncertainties.append({
            "question": "What happens if the MONGODB_URI is unreachable at startup? Does the app crash, retry, or serve degraded?",
            "context": "Code reads MONGODB_URI from env but error-handling of connection failures is not always visible.",
            "evidence": {
                "file": "scan-facts.json",
                "lines": [1, 1],
                "excerpt": "env var MONGODB_URI detected",
                "status": "code-verified",
            },
            "impact_if_wrong": "Cannot accurately describe the failure scenario in the readiness report.",
        })
    return uncertainties


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------


def _compute_session_identity(repo_root: Path) -> str:
    """Compute SHA-256 of (abs_repo_root + '|' + git_remote_url + '|' + git_head_hash).
    Falls back to '' for git_remote_url and git_head_hash when git is unavailable.
    """
    abs_root = str(repo_root.resolve())

    # Get git remote URL
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
        git_remote = r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        git_remote = ""

    # Get HEAD commit hash
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        git_head = r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        git_head = ""

    raw = abs_root + "|" + git_remote + "|" + git_head
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_graph(repo_root: Path, scan: Dict[str, Any], code: Dict[str, Any]) -> Dict[str, Any]:
    repo_root = repo_root.resolve()

    # Compute session identity at the top so it's available to all callers.
    session_identity = _compute_session_identity(repo_root)

    project = build_project(scan, repo_root)
    frontend = build_frontend(code)
    backend = build_backend(code)
    data = build_data(code)
    auth = build_auth(code, backend["routes"])
    user_flows = build_user_flows(backend["routes"])
    data_flows = build_data_flows(frontend["api_calls"], backend["routes"])
    risks = build_risks(code, scan)
    uncertainties = build_uncertainties(code, scan)

    return {
        "session_identity": session_identity,
        "project": project,
        "frontend": frontend,
        "backend": backend,
        "data": data,
        "auth": auth,
        "user_flows": user_flows,
        "data_flows": data_flows,
        "risks": risks,
        "uncertainties": uncertainties,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: build_graph.py <repo-root> [--no-validate] [--pretty]", file=sys.stderr)
        sys.exit(2)

    repo_root = Path(sys.argv[1]).resolve()
    if not repo_root.exists():
        print(f"Error: {repo_root} does not exist", file=sys.stderr)
        sys.exit(1)

    no_validate = "--no-validate" in sys.argv
    pretty = "--pretty" not in sys.argv  # pretty by default

    defense_dir = repo_root / ".project-defense"
    scan_path = defense_dir / "scan-facts.json"
    code_path = defense_dir / "code-facts.json"

    if not scan_path.exists():
        print(f"Error: {scan_path} not found. Run scripts/scan_repository.py first.", file=sys.stderr)
        sys.exit(1)
    if not code_path.exists():
        print(f"Error: {code_path} not found. Run scripts/detect_code_facts.py first.", file=sys.stderr)
        sys.exit(1)

    scan = json.loads(scan_path.read_text())
    code = json.loads(code_path.read_text())

    print(f"Building project graph for {repo_root}...")
    graph = build_graph(repo_root, scan, code)

    # Validate against schema
    schema_path = SCRIPT_DIR.parent / "templates" / "project-graph.schema.json"
    if not no_validate and validate_value is not None and schema_path.exists():
        schema = json.loads(schema_path.read_text())
        errors = validate_value(graph, schema, schema)
        if errors:
            print(f"ERROR: built graph has {len(errors)} schema violation(s):", file=sys.stderr)
            for e in errors[:10]:
                print(f"  - {e}", file=sys.stderr)
            print("Run with --no-validate to write anyway.", file=sys.stderr)
            sys.exit(1)

    # Write output
    graph_path = defense_dir / "project-graph.json"
    if pretty:
        graph_path.write_text(json.dumps(graph, indent=2))
    else:
        graph_path.write_text(json.dumps(graph))

    # Summary
    n_components = len(graph["frontend"]["components"])
    n_routes = len(graph["backend"]["routes"])
    n_models = len(graph["data"]["models"])
    n_auth = len(graph["auth"]["protected_routes"])
    n_unc = len(graph["uncertainties"])
    print(f"Written to {graph_path}")
    print(f"  components: {n_components}")
    print(f"  routes:     {n_routes}")
    print(f"  models:     {n_models}")
    print(f"  protected:  {n_auth}")
    print(f"  uncertainties (questions for Phase 4): {n_unc}")


if __name__ == "__main__":
    main()