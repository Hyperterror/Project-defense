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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Local import — works whether the script is run from any cwd
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
try:
    from validate_graph import validate_value
except ImportError:
    validate_value = None  # type: ignore

try:
    import apply_corrections
except ImportError:  # pragma: no cover - the script is shipped alongside
    apply_corrections = None  # type: ignore


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
    if not stack:
        # Nothing identifiable: no manifest, or a language this skill has no
        # pack for. Previously this produced `stack: []`, which the schema
        # rejects, so build_graph refused to write and every later phase failed
        # with "run build_graph.py first" -- a dead end with no way forward.
        # A named placeholder keeps the pipeline moving and says so in the graph.
        stack = ["undetermined"]

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


# A middleware or dependency name that reads like access control.
AUTH_GUARD_HINT = re.compile(
    r"(auth|user|admin|token|permission|login|current|guard|session|jwt|require)",
    re.I,
)


def build_backend(code: Dict[str, Any]) -> Dict[str, Any]:
    """Backend: routes, middleware, controllers, services."""
    express = code.get("express", {})

    # Every framework ends up in one route list: the graph is about *this*
    # project's API surface, not about which library serves it. Order is fixed
    # (Express, Python, Next.js) so the output stays deterministic.
    detected = list(express.get("routes", []))
    detected += list(code.get("python", {}).get("routes", []))
    detected += list(code.get("nextjs", {}).get("routes", []))
    # Generic packs (Go, Ruby, PHP, Java, C#, Rust, Kotlin, Elixir) produce the
    # same evidence shape, so they join the same list and dedupe the same way.
    detected += list(code.get("generic", {}).get("routes", []))

    # Rails protects a controller, not a route: join `before_action
    # :authenticate_user!` to every route that controller serves.
    guards = (code.get("generic") or {}).get("guards") or []
    guarded_controllers = {}
    for guard in guards:
        guarded_controllers[guard.get("controller", "")] = guard

    routes = []
    seen_routes = set()
    for r in detected:
        handler = r.get("handler")
        # The schema requires handler to be a string. When the detector could
        # not extract a named handler (e.g., for inline arrow functions), we
        # fall back to the route file basename so the graph validates. The
        # agent refines this in Phase 4 to a real function/closure name.
        if not handler:
            handler = Path(r["evidence"]["file"]).stem
        key = (r["method"], r["path"], handler)
        if key in seen_routes:
            continue
        seen_routes.add(key)
        entry = {
            "method": r["method"],
            "path": r["path"],
            "handler": handler,
            "evidence": r["evidence"],
        }
        middleware = [m for m in (r.get("middleware") or []) if m]
        handler = entry["handler"]
        controller = handler.split("#", 1)[0] if "#" in handler else ""
        if controller and controller in guarded_controllers:
            guard = guarded_controllers[controller]
            action = handler.split("#", 1)[1] if "#" in handler else ""
            if action not in (guard.get("except") or []):
                middleware.append(guard.get("guard", "before_action"))
        if middleware:
            entry["middleware"] = middleware
        routes.append(entry)

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


def _normalise_field(field: Any) -> Dict[str, Any]:
    """The schema wants {name, type}; packs sometimes only know a name."""
    if isinstance(field, dict):
        entry = {"name": str(field.get("name", "")), "type": str(field.get("type") or "unknown")}
        for flag in ("required", "unique", "indexed"):
            if field.get(flag) is not None:
                entry[flag] = bool(field[flag])
        if field.get("description"):
            entry["description"] = str(field["description"])
        return entry
    return {"name": str(field), "type": "unknown"}


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

    # Generic packs: Go structs, Rails/Eloquent/JPA entities, Prisma schemas,
    # Ecto schemas. Keyed by name so a model found twice is listed once.
    seen_models = {m["name"] for m in models}
    for m in code.get("generic", {}).get("models", []):
        if m.get("name") in seen_models:
            continue
        seen_models.add(m["name"])
        models.append({
            "name": m["name"],
            "fields": [_normalise_field(f) for f in m.get("fields", [])],
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
    session_count = len(auth_signals.get("session_auth", []))
    permission_count = len(auth_signals.get("permissions", []))
    provider_count = len(auth_signals.get("provider_auth", []))

    # Tier-2 packs report their own signals (token/hash/guard/permission/session)
    # per ecosystem. Without this a Rails project with Devise, bcrypt and a JWT
    # gem still reported `strategy: other`, and the interview asked nothing about
    # authentication it could see in the code.
    generic_auth = (code.get("generic") or {}).get("auth") or {}
    generic_token = len(generic_auth.get("token") or [])
    generic_hash = len(generic_auth.get("hash") or [])
    generic_guard = len(generic_auth.get("guard") or [])
    generic_permission = len(generic_auth.get("permission") or [])
    generic_session = len(generic_auth.get("session") or [])
    generic_api_key = len(generic_auth.get("api_key") or [])

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
    elif bcrypt_count > 0 or session_count > 0:
        strategy = "session"
        token_handling = (
            "Password hashing and/or framework session auth detected "
            "(login/authenticate); session or cookie-based auth likely. "
            "Confirm with user."
        )
    elif provider_count > 0:
        # Supabase / NextAuth / Auth.js: the credential check is delegated, and
        # the session lives in cookies the app only reads.
        strategy = "cookie"
        sample = auth_signals["provider_auth"][0]
        token_handling = (
            "Delegated auth provider detected (%s); the session is normally "
            "carried in cookies and checked per request. Confirm the exact "
            "cookie/refresh behaviour with the user."
            % sample["file"]
        )
    elif generic_api_key > 0:
        strategy = "API key"
        sample = (generic_auth.get("api_key") or [{}])[0]
        token_handling = (
            "Opaque access tokens detected in %s (%s) -- not JWTs. Confirm where the "
            "token is issued and how it is sent."
            % (sample.get("evidence", {}).get("file", "an unread file"),
               sample.get("match", "token"))
        )
    elif generic_token > 0:
        strategy = "JWT"
        sample = (generic_auth.get("token") or [{}])[0]
        token_handling = (
            "A JWT library is used in %s (%s). Confirm whether it issues tokens or "
            "only verifies them." % (sample.get("evidence", {}).get("file", "an unread file"),
                                     sample.get("match", "jwt"))
        )
    elif generic_hash > 0 or generic_session > 0:
        strategy = "session"
        sample = ((generic_auth.get("hash") or generic_auth.get("session")) or [{}])[0]
        token_handling = (
            "Password hashing and/or framework authentication detected in %s (%s); "
            "session or cookie-based auth likely. Confirm with the user."
            % (sample.get("evidence", {}).get("file", "an unread file"),
               sample.get("match", "hashing"))
        )
    elif generic_permission > 0 or generic_guard > 0:
        # Guards without any token code: the framework's own form login or
        # session is the common case (Spring Security, Devise, ASP.NET Identity).
        # Delegated cookie providers are reported separately as provider_auth.
        strategy = "session"
        sample = ((generic_auth.get("permission") or generic_auth.get("guard")) or [{}])[0]
        token_handling = (
            "Route guards detected in %s (%s) but no token code; the credential may "
            "live in a cookie or outside this repo. Confirm with the user."
            % (sample.get("evidence", {}).get("file", "an unread file"),
               sample.get("match", "guard"))
        )
    elif permission_count > 0:
        strategy = "other"
        token_handling = (
            "Permission classes detected but no token or hashing code found; "
            "the credential check may live outside this repo. Confirm with user."
        )
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
        # Two ways a route is protected, and they are both evidence:
        # an Express mount prefix, or a per-route guard the framework applies
        # itself (FastAPI `Depends(...)`, DRF `permission_classes`).
        guarded_by = [
            name for name in (r.get("middleware") or [])
            if AUTH_GUARD_HINT.search(name)
        ]
        by_prefix = any(r["path"].startswith(prefix) for prefix in protected_prefixes)
        if not (guarded_by or by_prefix):
            continue
        details = {"method": r["method"], "path": r["path"]}
        if guarded_by:
            details["guard"] = guarded_by[0]
        protected_routes.append({
            "name": f"{r['method']} {r['path']}",
            "details": details,
            "evidence": r["evidence"],
        })

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


def _dedupe_uncertainties(uncertainties: List[Dict[str, Any]]) -> None:
    """Two detectors can ask the same question; ask it once."""
    seen = set()
    unique = []
    for entry in uncertainties:
        key = (entry.get("question") or "").strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)
    uncertainties[:] = unique


def build_coverage_uncertainties(scan: Dict[str, Any], backend: Dict[str, Any],
                                 data: Dict[str, Any], code: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Say out loud when the analysis saw nothing.

    A project with zero routes and zero models is either an empty repository or a
    stack this skill cannot read. Both used to reach Phase 5 silently: the
    question bank fell back to generic questions and nothing in the graph hinted
    that the interview was not about this project. Each case is now a question
    the agent has to ask the user before generating anything.
    """
    entries: List[Dict[str, Any]] = []
    stack = (scan.get("frameworks") or {})
    has_stack = any(stack.get(k) for k in ("frontend", "backend", "database"))
    ecosystems = (code.get("generic") or {}).get("ecosystems", [])

    if not backend.get("routes") and not data.get("models"):
        entries.append({
            "question": (
                "The analysis found no routes and no models. Which framework serves "
                "this project's API, and which file defines its first route?"
            ),
            "context": (
                "No detector matched this repository. Supported route detectors are "
                "Express, Next.js, FastAPI, Flask, Django/DRF, Gin/Echo/Chi/Fiber, "
                "Rails, Laravel, Spring, ASP.NET, Axum/Actix, Ktor and Phoenix. "
                f"Ecosystems seen in the file tree: {', '.join(ecosystems) or 'none recognised'}."
            ),
            "evidence": {
                "file": "scan-facts.json",
                "lines": [1, 1],
                "excerpt": "no routes and no models detected",
                "status": "UNVERIFIED",
            },
            "impact_if_wrong": (
                "Every later question would be generic, so the interview would not "
                "test knowledge of this project."
            ),
        })
    if not has_stack:
        entries.append({
            "question": (
                "No dependency manifest was read, so the stack is unknown. What "
                "languages, frameworks and database does this project use?"
            ),
            "context": "Manifests read: package.json, requirements.txt and the lock/manifest files for go, cargo, composer, bundler, maven, gradle and mix. None yielded dependencies.",
            "evidence": {
                "file": "scan-facts.json",
                "lines": [1, 1],
                "excerpt": "frameworks: {}",
                "status": "UNVERIFIED",
            },
            "impact_if_wrong": "Trade-off and architecture questions would be about the wrong stack.",
        })
    return entries


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


def _get_git_head(repo_root: Path) -> str:
    """Return the current HEAD commit hash, or '' when git is unavailable."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _content_fingerprint(repo_root: Path) -> str:
    """Hash the project's source files (path, size, mtime) into one digest.

    Recorded so `check_graph_freshness.py` can still detect a stale graph in a
    repository with no git history, where a commit hash is not available.
    """
    try:
        from path_filters import load_ignore_patterns, walk_files
        from detect_code_facts import is_source_file
    except ImportError:
        return ""
    digest = hashlib.sha256()
    try:
        for path in walk_files(repo_root, load_ignore_patterns(repo_root)):
            if not is_source_file(path):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            rel = str(path.relative_to(repo_root)).replace("\\", "/")
            digest.update(("%s:%d:%d\n" % (rel, stat.st_size, stat.st_mtime_ns)).encode())
    except Exception:
        return ""
    return digest.hexdigest()


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


def build_relationships(code: Dict[str, Any], backend: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build the file-level edge list (the 'what breaks if I delete this' map).

    Edge types kept deliberately small:
      - imports:   file A pulls code from file B (regex-resolved, internal only)
      - tested_by: file A has a test file B by naming convention
      - protects:  middleware M guards route path P (from its mount prefix)

    A defense answer about deleting a module is only as good as its list of
    importers, so these edges are what turn that question from guesswork into
    evidence.
    """
    edges: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str]] = set()

    def add(edge_type: str, source: str, target: str, evidence: Dict[str, Any]) -> None:
        key = (edge_type, source, target)
        if key in seen or not source or not target:
            return
        seen.add(key)
        edges.append({
            "type": edge_type,
            "from": source,
            "to": target,
            "evidence": {
                "file": evidence.get("file", source),
                "lines": evidence.get("lines", [1, 1]),
                "excerpt": str(evidence.get("excerpt", ""))[:200],
                "status": evidence.get("status", "code-verified"),
            },
        })

    for item in code.get("imports", []) or []:
        add("imports", item.get("from", ""), item.get("to", ""), item.get("evidence", {}))

    for item in code.get("tests", []) or []:
        add("tested_by", item.get("source", ""), item.get("test", ""), item.get("evidence", {}))

    # A middleware mounted at a prefix protects every route under that prefix.
    for middleware in backend.get("middleware", []) or []:
        prefix = (middleware.get("details", {}) or {}).get("path_prefix")
        if not prefix:
            continue
        for route in backend.get("routes", []) or []:
            path = route.get("path") or ""
            if path.startswith(prefix):
                add(
                    "protects",
                    str(middleware.get("name", "")),
                    path,
                    middleware.get("evidence", {}) or route.get("evidence", {}),
                )

    # Deterministic order, and bounded so a huge repo cannot bloat the graph.
    edges.sort(key=lambda e: (e["type"], e["from"], e["to"]))
    return edges[:500]


def build_graph(repo_root: Path, scan: Dict[str, Any], code: Dict[str, Any]) -> Dict[str, Any]:
    repo_root = repo_root.resolve()

    # Compute session identity at the top so it's available to all callers.
    session_identity = _compute_session_identity(repo_root)

    project = build_project(scan, repo_root)
    frontend = build_frontend(code)
    backend = build_backend(code)
    data = build_data(code)
    auth = build_auth(code, backend["routes"])
    relationships = build_relationships(code, backend)
    user_flows = build_user_flows(backend["routes"])
    data_flows = build_data_flows(frontend["api_calls"], backend["routes"])
    risks = build_risks(code, scan)
    uncertainties = build_uncertainties(code, scan)
    uncertainties.extend(build_coverage_uncertainties(scan, backend, data, code))
    _dedupe_uncertainties(uncertainties)

    graph = {
        "session_identity": session_identity,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "git_head": _get_git_head(repo_root),
        "content_fingerprint": _content_fingerprint(repo_root),
        "project": project,
        "frontend": frontend,
        "backend": backend,
        "data": data,
        "auth": auth,
        "user_flows": user_flows,
        "data_flows": data_flows,
        "relationships": relationships,
        "risks": risks,
        "uncertainties": uncertainties,
    }

    # Phase 4 answers outlive a rebuild: without this the graph was always the
    # machine's first guess, and corrections.json was written and never read.
    if apply_corrections is not None:
        graph["_corrections"] = apply_corrections.apply_from_disk(repo_root, graph)

    return graph


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
    corrections = graph.pop("_corrections", {"applied": [], "unmatched": []})
    if corrections.get("applied"):
        print(f"Corrections applied: {len(corrections['applied'])}")
    if corrections.get("unmatched"):
        print(
            "Corrections that matched nothing in this graph (the code may have "
            "changed; re-ask rather than assume they landed):",
            file=sys.stderr,
        )
        for entry_id in corrections["unmatched"]:
            print(f"  - {entry_id}", file=sys.stderr)

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