#!/usr/bin/env python3
"""
detect_code_facts.py -- Stack-specific code detectors for project-defense-skill.

Reads .project-defense/scan-facts.json (or scans a repo), then extracts:
  - Express routes (router.METHOD(path, ...), app.METHOD(...))
  - Express middleware (app.use(...), router.use(...))
  - FastAPI / Flask routes (decorators: @app.get('/x'), @app.route('/x', methods=[...]))
  - Django URLconf routes (path('x', view), include(...)) and DRF router registrations
  - Next.js file-based routes (app/api/**/route.ts exports, pages/api/**/*.ts)
  - React components (default exports of functions/arrows, function declarations)
  - React hooks (custom hooks from src/hooks/)
  - Mongoose models (mongoose.model(name, schema))
  - API calls from frontend (axios.get/post, fetch(url, {method}))
  - Authentication signals (JWT verify, bcrypt, password hashing, Django/DRF auth)
  - Environment variables used in code

Writes results to .project-defense/code-facts.json. Stdlib only, Python 3.8+.

This is Phase 2 of the workflow: deterministic fact extraction so the agent
does not have to guess.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from path_filters import (  # noqa: E402
    is_ignored,
    load_ignore_patterns,
    walk_files,
)


# ----------------------------------------------------------------------
# Directories to skip (noise / secrets / dependencies)
# ----------------------------------------------------------------------

SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", ".svn", ".hg",
    "dist", "build", "out", "target", ".next", ".nuxt",
    "venv", ".venv", "env", ".env",
    "vendor", "Pods", "DerivedData",
    ".idea", ".vscode", ".DS_Store",
    "coverage", ".nyc_output", ".pytest_cache",
    "examples", "docs",  # often contain documented-not-implemented code
}

# File extensions we scan
JS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
PY_EXTS = {".py"}

# ----------------------------------------------------------------------
# Regex patterns (compiled once)
# ----------------------------------------------------------------------

# Express routes: router.get('/path', ...), app.post('/path', ...), etc.
# Captures: (method, path, handler_or_middleware_args)
RE_EXPRESS_ROUTE = re.compile(
    r"""\b(router|app|server)\s*\.\s*(get|post|put|patch|delete|options|head|all)\s*\(\s*(['"`])([^'"`]+)\3""",
    re.IGNORECASE,
)

# Express middleware: app.use(middleware), app.use('/path', middleware)
# Captures: (receiver, optional path prefix, first middleware arg)
RE_EXPRESS_MIDDLEWARE = re.compile(
    r"""\b(router|app|server)\s*\.\s*use\s*\((['"])([^'"]+)\2\s*,\s*([A-Za-z_][\w]*)""",
)

# Mongoose: mongoose.model('Name', schema) or model('Name', schema)
RE_MONGOOSE_MODEL = re.compile(
    r"""\b(?:mongoose\.)?model\s*\(\s*(['"`])([A-Z][A-Za-z0-9_]*)\1""",
)

# Mongoose schema: new mongoose.Schema({ ... })
RE_MONGOOSE_SCHEMA = re.compile(
    r"""\bnew\s+(?:mongoose\.)?Schema\s*\(""",
)

# React component: function declaration or arrow with default export
# Captures: function name
RE_REACT_COMPONENT = re.compile(
    r"""(?:export\s+default\s+function\s+([A-Z][A-Za-z0-9_]*))|"""
    r"""(?:export\s+default\s+const\s+([A-Z][A-Za-z0-9_]*)\s*=\s*(?:\([^)]*\)|[A-Za-z_]+)\s*=>)|"""
    r"""(?:export\s+default\s+\(\s*\)?\s*=>)|"""
    r"""(?:^const\s+([A-Z][A-Za-z0-9_]*)\s*=\s*(?:\([^)]*\)|[A-Za-z_]+)\s*=>)|"""
    r"""(?:^function\s+([A-Z][A-Za-z0-9_]*)\s*\()""",
    re.MULTILINE,
)

# React hook: function starting with `use`
RE_REACT_HOOK = re.compile(
    r"""(?:export\s+(?:default\s+)?(?:const|function)\s+(use[A-Z][A-Za-z0-9_]*))""",
)

# axios.get / axios.post / axios.put / axios.delete / axios.patch
RE_AXIOS_CALL = re.compile(
    r"""\baxios\s*\.\s*(get|post|put|patch|delete)\s*\(\s*(['"`])([^'"`]+)\2""",
    re.IGNORECASE,
)

# fetch('url', { method: 'POST' })
RE_FETCH_CALL = re.compile(
    r"""\bfetch\s*\(\s*(['"`])([^'"`]+)\1""",
)

# JWT verify: jwt.verify(token, secret)
RE_JWT_VERIFY = re.compile(r"""\bjwt\s*\.\s*verify\s*\(""")

# bcrypt: bcrypt.hash / bcrypt.compare / bcrypt.genSalt
RE_BCRYPT = re.compile(r"""\bbcrypt\s*\.\s*(hash|compare|genSalt|hashSync|compareSync)\s*\(""")

# Password field references (heuristic)
RE_PASSWORD = re.compile(r"""\b(password|passwd|pwd)\b""", re.IGNORECASE)

# Delegated auth: the provider owns the session, the app only reads cookies.
RE_JS_PROVIDER_AUTH = re.compile(
    r"@supabase/ssr|@supabase/auth-helpers-nextjs|supabase\.auth\.(?:getUser|getSession|signIn)"
    r"|next-auth|signIn\s*\(|useSession\s*\(|auth\(\)\s*\."
)

# Python auth signals -- the same three facts under different names.
RE_PY_JWT_SIGNAL = re.compile(r"\bjwt\s*\.\s*(?:encode|decode)\s*\(")
RE_PY_HASH_SIGNAL = re.compile(
    r"\bCryptContext\s*\(|\bpasslib\b|\bbcrypt\s*\.\s*(?:hashpw|checkpw|gensalt)\s*\("
    r"|\bpwd_context\s*\.\s*(?:hash|verify)\s*\("
)
RE_PY_SESSION_SIGNAL = re.compile(
    r"\bauthenticate\s*\(|\bdjango\.contrib\.auth\b|@login_required\b|\blogin\s*\(request"
)
RE_PY_PERMISSION_SIGNAL = re.compile(
    r"\bIsAuthenticated\b|\bIsAdminUser\b|\bJWTAuthentication\b"
    r"|\bpermission_classes\s*=|@permission_required\b"
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def should_skip(path: Path, root: Path, patterns: Optional[List[str]] = None) -> bool:
    """Skip files in noise/dependency/secret directories or ignored paths."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    parts = rel.parts
    for p in parts[:-1]:  # check parent dirs
        if p in SKIP_DIRS or p.startswith("."):
            return True
    if patterns and is_ignored(rel, patterns):
        return True
    return False


def is_source_file(path: Path) -> bool:
    return path.suffix.lower() in JS_EXTS or path.suffix.lower() in PY_EXTS


def read_text(path: Path, max_chars: int = 100_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except Exception:
        return ""


def find_lines(text: str, match_start: int) -> int:
    """Return 1-based line number for a character offset."""
    return text.count("\n", 0, match_start) + 1


def make_excerpt(text: str, start: int, end: int, max_len: int = 120) -> str:
    excerpt = text[start:end].strip()
    # collapse whitespace
    excerpt = re.sub(r"\s+", " ", excerpt)
    if len(excerpt) > max_len:
        excerpt = excerpt[:max_len - 3] + "..."
    return excerpt


def evidence(file: Path, root: Path, line_no: int, excerpt: str) -> Dict[str, Any]:
    return {
        "file": str(file.relative_to(root)),
        "lines": [line_no, line_no],
        "excerpt": excerpt,
        "status": "code-verified",
    }


# ----------------------------------------------------------------------
# Import graph (file -> file edges)
# ----------------------------------------------------------------------

# `import x from "y"`, `export * from "y"`, `require("y")`, `import("y")`
RE_JS_IMPORT = re.compile(
    r"(?:\bfrom\s*|\brequire\s*\(\s*|\bimport\s*\(\s*|^\s*import\s+)['\"]([^'\"]+)['\"]",
    re.M,
)
# `from .models import X` / `import server.models`
RE_PY_IMPORT = re.compile(
    r"^\s*(?:from\s+([.\w]+)\s+import|import\s+([.\w]+))", re.M
)

JS_RESOLVE_EXTS = [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".json"]
PY_RESOLVE_EXTS = [".py"]


def _resolve_js_module(spec: str, from_file: Path, root: Path) -> Optional[Path]:
    """Resolve a relative JS/TS specifier to a file inside the repo."""
    if not spec.startswith("."):
        return None  # bare specifier: a dependency, not a project edge
    base = (from_file.parent / spec).resolve()
    candidates = [base] + [base.with_name(base.name + ext) for ext in JS_RESOLVE_EXTS]
    candidates += [base / ("index" + ext) for ext in JS_RESOLVE_EXTS]
    for candidate in candidates:
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


def _resolve_py_module(spec: str, from_file: Path, root: Path) -> Optional[Path]:
    """Resolve a Python `from a.b import c` specifier to a file inside the repo."""
    if not spec or spec in ("import", "from"):
        return None
    if spec.startswith("."):
        # Relative import: walk up one level per leading dot.
        depth = len(spec) - len(spec.lstrip("."))
        base = from_file.parent
        for _ in range(max(depth - 1, 0)):
            base = base.parent
        parts = [p for p in spec.lstrip(".").split(".") if p]
    else:
        base = root
        parts = [p for p in spec.split(".") if p]
    target = base.joinpath(*parts)
    for candidate in [target.with_name(target.name + ".py"), target / "__init__.py"]:
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


def detect_imports(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    """Extract internal file-to-file import edges (stdlib regex, no parser).

    Only edges between files of *this* project are recorded: a bare specifier
    (`react`, `express`) names a dependency, and counting it would drown the
    graph in noise. The edges are what make 'what breaks if I delete this?'
    answerable with evidence instead of guesswork.
    """
    edges: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str]] = set()
    for path in files:
        suffix = path.suffix.lower()
        text = read_text(path)
        if not text:
            continue
        if suffix in JS_EXTS:
            pattern, resolver = RE_JS_IMPORT, _resolve_js_module
        elif suffix in PY_EXTS:
            pattern, resolver = RE_PY_IMPORT, _resolve_py_module
        else:
            continue
        for match in pattern.finditer(text):
            spec = (match.group(1) or (match.group(2) if match.re is RE_PY_IMPORT else "") or "")
            if not spec:
                continue
            target = resolver(spec, path, root)
            if target is None or target == path:
                continue
            source_rel = str(path.relative_to(root))
            target_rel = str(target.relative_to(root))
            key = (source_rel, target_rel)
            if key in seen:
                continue
            seen.add(key)
            edges.append({
                "from": source_rel,
                "to": target_rel,
                "spec": spec,
                "evidence": evidence(
                    path, root, find_lines(text, match.start()), spec
                ),
            })
    return edges


# ----------------------------------------------------------------------
# Detectors
# ----------------------------------------------------------------------


def detect_express_middleware(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    """Find Express middleware registrations, including router mounts."""
    mw: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, Optional[str]]] = set()
    for f in files:
        if should_skip(f, root):
            continue
        if f.suffix.lower() not in JS_EXTS:
            continue
        text = read_text(f)
        # Form 1: app.use('/path', router/middleware) -- with path prefix
        # Captures only the FIRST arg after the path. The route detector's mount
        # resolution iterates over all identifiers in the call to handle 3-arg form.
        for m in re.finditer(
            r"""\b(app|server)\s*\.\s*use\s*\((['"])([^'"]+)\2\s*,\s*([A-Za-z_][\w]*)""",
            text,
        ):
            mount_path = m.group(3)
            sub_name = m.group(4)
            line_no = find_lines(text, m.start())
            key = (sub_name, mount_path)
            if key in seen:
                continue
            seen.add(key)
            mw.append({
                "name": sub_name,
                "path_prefix": mount_path,
                "evidence": evidence(f, root, line_no, make_excerpt(text, m.start(), m.end() + 50)),
            })
        # Form 2: app.use(middleware) -- no path prefix. Allow optional function call: `app.use(cors())`
        for m in re.finditer(
            r"""\b(router|app|server)\s*\.\s*use\s*\(\s*([A-Za-z_][\w.]*)(?:\s*\(\s*\))?\s*\)""",
            text,
        ):
            receiver = m.group(1)
            mw_name = m.group(2)
            line_no = find_lines(text, m.start())
            key = (mw_name, None)
            if key in seen:
                continue
            seen.add(key)
            mw.append({
                "name": mw_name,
                "path_prefix": None,
                "evidence": evidence(f, root, line_no, make_excerpt(text, m.start(), m.end() + 50)),
            })
    return mw


def detect_express_routes(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    """Find Express route definitions across JS/TS files. Applies mount prefixes from app.use()."""
    # First pass: build a map of `const X = require('./routes/Y')` so we can connect
    # `app.use('/api/foo', X)` -> the routes/Y.js file's router -> prefix '/api/foo'
    file_to_router_var: Dict[Path, str] = {}
    for f in files:
        if should_skip(f, root):
            continue
        if f.suffix.lower() not in JS_EXTS:
            continue
        text = read_text(f)
        # Detect this file's router variable: `const router = express.Router()` or `const X = express.Router()`
        m = re.search(r"const\s+(\w+)\s*=\s*express\.Router\(\)", text)
        if m:
            file_to_router_var[f] = m.group(1)

    # Second pass: build mounts. Two ways to discover them:
    #   (a) same file: `app.use('/api/auth', authRoutes)` where authRoutes is `const authRoutes = require('./routes/auth')`
    #   (b) in any file: `app.use('/api/auth', router)` where the routes are defined right here
    mounts_by_var: Dict[str, str] = {}  # router variable name -> mount path
    mounts_by_file: Dict[Path, str] = {}  # routes file path -> mount path (when the routes file uses `module.exports = router`)
    for f in files:
        if should_skip(f, root):
            continue
        if f.suffix.lower() not in JS_EXTS:
            continue
        text = read_text(f)
        # (a) app.use('/path', require('./routes/...')) -- inline mount
        for m in re.finditer(
            r"""\b(app|server)\s*\.\s*use\s*\((['"])([^'"]+)\2\s*,\s*require\s*\(\s*(['"])([^'"]+)\4""",
            text,
        ):
            mount_path = m.group(3)
            require_target = m.group(5)
            # Resolve "./routes/auth" -> server/routes/auth.js (or .ts)
            target_path = (f.parent / require_target).resolve()
            for ext in ("", ".js", ".ts", ".mjs", ".cjs"):
                candidate = target_path.with_suffix(target_path.suffix + ext) if ext else Path(str(target_path) + ".js")
                if candidate.exists():
                    mounts_by_file[candidate] = mount_path
                    break
        # (b) app.use('/path', mw, router) or app.use('/path', router) -- iterate over all identifiers
        # For each app.use('/path', ...) call, collect every identifier argument and resolve its require.
        for m_var_use in re.finditer(
            r"""\b(app|server)\s*\.\s*use\s*\((['"])([^'"]+)\2\s*,""",
            text,
        ):
            mount_path = m_var_use.group(3)
            # Find the matching close paren at depth 0 in the rest of the text
            rest = text[m_var_use.end():m_var_use.end() + 500]
            depth = 1
            end_idx = len(rest)
            for i, ch in enumerate(rest):
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    if depth == 0:
                        end_idx = i
                        break
            call_body = rest[:end_idx]
            # Find every identifier in the call body
            ident_names = [im.group(1) for im in re.finditer(r"""\b([A-Za-z_][\w]*)\b""", call_body)]
            for used_var in ident_names:
                # Find the require that binds this specific variable
                require_re = re.compile(
                    rf"""const\s+{re.escape(used_var)}\s*=\s*require\s*\(\s*(['"])([^'"]+)\1\s*\)"""
                )
                req_m = require_re.search(text)
                if not req_m:
                    continue
                require_target = req_m.group(2)
                if not require_target.startswith("."):
                    continue  # skip package requires
                target_path = (f.parent / require_target).resolve()
                resolved_target = None
                for ext in ("", ".js", ".ts", ".mjs"):
                    candidate = Path(str(target_path) + ext)
                    if candidate.exists():
                        resolved_target = candidate
                        break
                if resolved_target is None:
                    continue
                mounts_by_file[resolved_target] = mount_path
                mounts_by_var[used_var] = mount_path

    # Third pass: extract routes, applying the mount prefix
    routes: List[Dict[str, Any]] = []
    for f in files:
        if should_skip(f, root):
            continue
        if f.suffix.lower() not in JS_EXTS:
            continue
        text = read_text(f)
        mount_prefix = mounts_by_file.get(f)
        for m in RE_EXPRESS_ROUTE.finditer(text):
            method = m.group(2).upper()
            path = m.group(4)
            if mount_prefix and not path.startswith(mount_prefix):
                full_path = mount_prefix.rstrip("/") + (path if path.startswith("/") else "/" + path)
            else:
                full_path = path
            line_no = find_lines(text, m.start())
            after = text[m.end():m.end() + 300]
            handler_match = re.match(r"""\s*,?\s*([A-Za-z_][\w.]*)""", after)
            handler = handler_match.group(1) if handler_match else None
            # Filter out JS keywords and common non-handler tokens (e.g., 'async' before arrow fns)
            if handler in ("async", "function", "const", "let", "var", "await"):
                handler = None
            routes.append({
                "method": method,
                "path": full_path,
                "handler": handler,
                "evidence": evidence(f, root, line_no, make_excerpt(text, m.start(), m.end() + 40)),
            })
    return routes


def detect_mongoose_models(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    """Find Mongoose model definitions."""
    models: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for f in files:
        if should_skip(f, root):
            continue
        if f.suffix.lower() not in JS_EXTS:
            continue
        text = read_text(f)
        for m in RE_MONGOOSE_MODEL.finditer(text):
            name = m.group(2)
            if name in seen:
                continue
            seen.add(name)
            line_no = find_lines(text, m.start())
            models.append({
                "name": name,
                "fields": [],  # Field-level extraction is a follow-up
                "evidence": evidence(f, root, line_no, make_excerpt(text, m.start(), m.end() + 30)),
            })
    return models


# Python ORM models (SQLAlchemy + Django)
RE_SQLALCHEMY_MODEL = re.compile(
    r"""^class\s+(\w+)\s*\(\s*Base\s*\)\s*:\s*$\s*\n\s*__tablename__\s*=\s*(['"])([^'"]+)\2""",
    re.MULTILINE,
)
RE_DJANGO_MODEL = re.compile(
    r"""^class\s+(\w+)\s*\(\s*models\.Model\s*\)\s*:""",
    re.MULTILINE,
)


def detect_python_orm_models(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    """Find SQLAlchemy and Django model definitions in Python files."""
    models: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for f in files:
        if should_skip(f, root):
            continue
        if f.suffix.lower() not in PY_EXTS:
            continue
        text = read_text(f)
        for m in RE_SQLALCHEMY_MODEL.finditer(text):
            name = m.group(1)
            if name in seen:
                continue
            seen.add(name)
            line_no = find_lines(text, m.start())
            models.append({
                "name": name,
                "fields": [],
                "framework": "sqlalchemy",
                "evidence": evidence(f, root, line_no, make_excerpt(text, m.start(), m.end() + 60)),
            })
        for m in RE_DJANGO_MODEL.finditer(text):
            name = m.group(1)
            if name in seen:
                continue
            seen.add(name)
            line_no = find_lines(text, m.start())
            models.append({
                "name": name,
                "fields": [],
                "framework": "django",
                "evidence": evidence(f, root, line_no, make_excerpt(text, m.start(), m.end() + 30)),
            })
    return models


def detect_react_components(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    """Find React component definitions."""
    components: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for f in files:
        if should_skip(f, root):
            continue
        if f.suffix.lower() not in JS_EXTS:
            continue
        # Only consider files in src/ or components/ or pages/
        rel = f.relative_to(root)
        if not (any(part in rel.parts for part in ["src", "components", "pages", "app"])):
            continue
        text = read_text(f)
        for m in RE_REACT_COMPONENT.finditer(text):
            # group 1 = function decl w/export default
            # group 2 = const arrow w/export default
            # group 3 = anonymous arrow w/export default
            # group 4 = top-level const arrow
            # group 5 = top-level function decl
            name = m.group(1) or m.group(2) or m.group(3) or m.group(4) or m.group(5)
            if not name or name in seen:
                continue
            seen.add(name)
            line_no = find_lines(text, m.start())
            components.append({
                "name": name,
                "details": {"type": "component"},
                "evidence": evidence(f, root, line_no, make_excerpt(text, m.start(), m.end() + 40)),
            })
    return components


def detect_react_hooks(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    """Find custom React hook definitions (functions starting with `use`)."""
    hooks: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for f in files:
        if should_skip(f, root):
            continue
        if f.suffix.lower() not in JS_EXTS:
            continue
        rel = f.relative_to(root)
        if not (any(part in rel.parts for part in ["hooks", "src"])):
            continue
        text = read_text(f)
        for m in RE_REACT_HOOK.finditer(text):
            name = m.group(1)
            if name in seen:
                continue
            seen.add(name)
            line_no = find_lines(text, m.start())
            hooks.append({
                "name": name,
                "details": {"type": "hook"},
                "evidence": evidence(f, root, line_no, make_excerpt(text, m.start(), m.end() + 40)),
            })
    return hooks


def detect_api_calls(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    """Find API calls from frontend (axios/fetch)."""
    calls: List[Dict[str, Any]] = []
    for f in files:
        if should_skip(f, root):
            continue
        if f.suffix.lower() not in JS_EXTS:
            continue
        rel = f.relative_to(root)
        if not (any(part in rel.parts for part in ["src", "app", "client", "api", "services"])):
            continue
        text = read_text(f)
        for m in RE_AXIOS_CALL.finditer(text):
            method = m.group(1).upper()
            path = m.group(3)
            line_no = find_lines(text, m.start())
            calls.append({
                "name": f"axios.{method.lower()}:{path}",
                "details": {"method": method, "endpoint": path, "client": "axios"},
                "evidence": evidence(f, root, line_no, make_excerpt(text, m.start(), m.end() + 30)),
            })
        for m in RE_FETCH_CALL.finditer(text):
            path = m.group(2)
            line_no = find_lines(text, m.start())
            # Detect method if present
            after = text[m.end():m.end() + 200]
            method_match = re.search(r"""method\s*:\s*['"`](GET|POST|PUT|PATCH|DELETE)['"`]""", after)
            method = method_match.group(1) if method_match else "GET"
            calls.append({
                "name": f"fetch:{path}",
                "details": {"method": method, "endpoint": path, "client": "fetch"},
                "evidence": evidence(f, root, line_no, make_excerpt(text, m.start(), m.end() + 40)),
            })
    return calls


def detect_auth_signals(root: Path, files: List[Path]) -> Dict[str, Any]:
    """Find authentication-related code patterns (JS and Python)."""
    result: Dict[str, Any] = {
        "jwt_verify": [],
        "bcrypt_usage": [],
        "password_handling": [],
        "session_auth": [],
        "permissions": [],
        "provider_auth": [],
    }
    for f in files:
        if should_skip(f, root):
            continue
        suffix = f.suffix.lower()
        if suffix not in JS_EXTS and suffix not in PY_EXTS:
            continue
        text = read_text(f)
        if suffix in PY_EXTS:
            # Python stacks keep the same three facts under different names:
            # jose/PyJWT for tokens, passlib/bcrypt for hashing, and Django's
            # own auth for sessions and permissions.
            for match in RE_PY_JWT_SIGNAL.finditer(text):
                result["jwt_verify"].append(evidence(
                    f, root, find_lines(text, match.start()),
                    make_excerpt(text, match.start(), match.end() + 40),
                ))
            for match in RE_PY_HASH_SIGNAL.finditer(text):
                result["bcrypt_usage"].append({
                    "call": match.group(0).strip(),
                    "evidence": evidence(
                        f, root, find_lines(text, match.start()),
                        make_excerpt(text, match.start(), match.end() + 40),
                    ),
                })
            for match in RE_PY_SESSION_SIGNAL.finditer(text):
                result["session_auth"].append(evidence(
                    f, root, find_lines(text, match.start()),
                    make_excerpt(text, match.start(), match.end() + 40),
                ))
            for match in RE_PY_PERMISSION_SIGNAL.finditer(text):
                result["permissions"].append({
                    "name": match.group(0).strip(),
                    "evidence": evidence(
                        f, root, find_lines(text, match.start()),
                        make_excerpt(text, match.start(), match.end() + 40),
                    ),
                })
            continue
        for m in RE_JS_PROVIDER_AUTH.finditer(text):
            result["provider_auth"].append(evidence(
                f, root, find_lines(text, m.start()),
                make_excerpt(text, m.start(), m.end() + 40),
            ))
        for m in RE_JWT_VERIFY.finditer(text):
            line_no = find_lines(text, m.start())
            result["jwt_verify"].append(evidence(f, root, line_no, make_excerpt(text, m.start(), m.end() + 40)))
        for m in RE_BCRYPT.finditer(text):
            line_no = find_lines(text, m.start())
            result["bcrypt_usage"].append({
                "call": m.group(1),
                "evidence": evidence(f, root, line_no, make_excerpt(text, m.start(), m.end() + 40)),
            })
    return result


# ----------------------------------------------------------------------
# Python web routes (FastAPI, Flask, Django, DRF)
# ----------------------------------------------------------------------

# @app.get('/x') / @router.post("/x") / @bp.delete('/x')
RE_PY_DECORATOR_ROUTE = re.compile(
    r"^[ \t]*@[ \t]*([A-Za-z_][\w.]*)[ \t]*\.[ \t]*"
    r"(get|post|put|patch|delete|options|head)[ \t]*\([ \t]*(['\"])([^'\"]*)\3",
    re.M,
)
# @app.route('/x', methods=['POST'])
RE_PY_DECORATOR_FLASK = re.compile(
    r"^[ \t]*@[ \t]*([A-Za-z_][\w.]*)[ \t]*\.route[ \t]*\([ \t]*(['\"])([^'\"]*)\2",
    re.M,
)
# router = APIRouter(prefix="/tasks")
RE_PY_ROUTER_PREFIX = re.compile(r"\b([A-Za-z_]\w*)\s*=\s*(?:fastapi\.)?APIRouter\s*\(")
# Depends(get_current_user)
RE_PY_DEPENDS = re.compile(r"Depends\s*\(\s*([A-Za-z_][\w.]*)")
# Django: path(...) / re_path(...) / url(...)
RE_DJANGO_PATH_CALL = re.compile(r"\b(re_path|path|url)\s*\(")
# DRF: router = DefaultRouter() / SimpleRouter()
RE_DRF_ROUTER_VAR = re.compile(r"\b([A-Za-z_]\w*)\s*=\s*\w*Router\s*\(")
# DRF: router.register(r"posts", PostViewSet, basename="post")
RE_DRF_REGISTER = re.compile(
    r"\b([A-Za-z_]\w*)\s*\.\s*register\s*\(\s*(?:r?['\"]([^'\"]+)['\"]|"
    r"([A-Za-z_][\w.]*))\s*,\s*([A-Za-z_][\w.]*)"
)
RE_PY_VIEW_DEF = re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+([A-Za-z_]\w*)[ \t]*\(", re.M)
RE_REQUIRE_METHODS = re.compile(r"@require_http_methods\s*\(\s*\[([^\]]*)\]")
RE_DRF_API_VIEW = re.compile(r"@api_view\s*\(\s*\[([^\]]*)\]")
RE_REQUIRE_SINGLE = re.compile(r"@require_(POST|GET|PUT|PATCH|DELETE)\b")
RE_CLASS_VIEWSET = re.compile(r"^[ \t]*class[ \t]+(\w+)[ \t]*\(([^)]*)\)[ \t]*:", re.M)

# A dependency name that reads like access control rather than plumbing.
AUTH_DEPENDENCY_HINT = re.compile(
    r"(auth|user|admin|token|permission|login|current|guard|session|jwt|require)",
    re.I,
)

HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD")


# CRUD methods a DRF viewset class serves, and the action each one maps to.
VIEWSET_ACTIONS = {
    "ModelViewSet": [
        ("GET", "list", ""), ("POST", "create", ""),
        ("GET", "retrieve", "/{id}"), ("PUT", "update", "/{id}"),
        ("PATCH", "partial_update", "/{id}"), ("DELETE", "destroy", "/{id}"),
    ],
    "ReadOnlyModelViewSet": [
        ("GET", "list", ""), ("GET", "retrieve", "/{id}"),
    ],
}


def _join_path(*parts: Optional[str]) -> str:
    """Join URL fragments into one absolute path ('/api/auth/register')."""
    segments = []
    for part in parts:
        if not part:
            continue
        cleaned = part.strip()
        if cleaned in ("", "^", "$", "^$"):
            continue
        # Regex-style Django patterns: drop anchors, keep the literal text.
        cleaned = cleaned.strip("^").strip("$")
        cleaned = cleaned.replace("^", "").replace("$", "")
        for segment in cleaned.split("/"):
            if segment:
                segments.append(segment)
    return "/" + "/".join(segments)


def _balanced_call(text: str, open_idx: int) -> Tuple[str, int]:
    """Return the arguments of the call whose '(' sits at open_idx, and its end."""
    depth = 0
    i = open_idx
    while i < len(text):
        ch = text[i]
        if ch in "'\"":
            quote = ch
            i += 1
            while i < len(text) and text[i] != quote:
                if text[i] == "\\":
                    i += 1
                i += 1
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i], i
        i += 1
    return "", len(text)


def _split_args(inner: str) -> List[str]:
    """Split a call's argument string on top-level commas."""
    args: List[str] = []
    depth = 0
    current: List[str] = []
    quote = None
    for ch in inner:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    if current:
        args.append("".join(current).strip())
    return args


def _string_literal(expr: str) -> Optional[str]:
    """Return the value of a Python string literal, or None if it is not one."""
    match = re.match(r"^[rRbBuU]?(['\"])(.*)\1$", expr.strip(), re.S)
    return match.group(2) if match else None


def _python_signature(text: str, def_start: int, limit: int = 1200) -> str:
    """Return the parameter list of the function whose `def` starts at def_start."""
    open_idx = text.find("(", def_start)
    if open_idx == -1 or open_idx - def_start > limit:
        return ""
    inner, _end = _balanced_call(text, open_idx)
    return inner


def _route_dependencies(signature: str) -> List[str]:
    """Auth-looking `Depends(...)` names in a signature, e.g. get_current_user."""
    names = []
    for match in RE_PY_DEPENDS.finditer(signature):
        name = match.group(1).split(".")[-1]
        if AUTH_DEPENDENCY_HINT.search(name) and name not in names:
            names.append(name)
    return names


def _methods_from_decorators(prefix_text: str) -> List[str]:
    """HTTP methods implied by the decorators directly above a view function."""
    for match in RE_REQUIRE_METHODS.finditer(prefix_text):
        methods = [m.strip().strip("'\"").upper() for m in match.group(1).split(",")]
        methods = [m for m in methods if m in HTTP_METHODS]
        if methods:
            return methods
    for match in RE_DRF_API_VIEW.finditer(prefix_text):
        methods = [m.strip().strip("'\"").upper() for m in match.group(1).split(",")]
        methods = [m for m in methods if m in HTTP_METHODS]
        if methods:
            return methods
    single = RE_REQUIRE_SINGLE.search(prefix_text)
    if single:
        return [single.group(1)]
    return []


def detect_python_decorator_routes(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    """FastAPI and Flask routes, declared as decorators above a view function.

    `@app.get('/tasks')` and `@app.route('/tasks', methods=['POST'])` are the
    same fact expressed two ways, so both land in one list. A route is marked
    protected when its signature takes an auth-looking `Depends(...)`, which is
    how FastAPI expresses access control.
    """
    routes: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str]] = set()
    for f in files:
        if should_skip(f, root) or f.suffix.lower() not in PY_EXTS:
            continue
        text = read_text(f)
        if not text:
            continue

        # Router prefixes: `router = APIRouter(prefix="/tasks")`.
        prefixes: Dict[str, str] = {}
        for match in RE_PY_ROUTER_PREFIX.finditer(text):
            inner, _end = _balanced_call(text, text.find("(", match.start()))
            prefix_match = re.search(
                r"\bprefix\s*=\s*(['\"])([^'\"]*)\1", inner
            )
            if prefix_match:
                prefixes[match.group(1)] = prefix_match.group(2)

        decorators: List[Tuple[int, str, List[str], Optional[str]]] = []
        for match in RE_PY_DECORATOR_ROUTE.finditer(text):
            receiver = match.group(1).split(".")[0]
            decorators.append((
                match.start(),
                match.group(2).upper(),
                [match.group(4)],
                prefixes.get(receiver),
            ))
        for match in RE_PY_DECORATOR_FLASK.finditer(text):
            receiver = match.group(1).split(".")[0]
            decorators.append((
                match.start(),
                "GET",
                [match.group(3)],
                prefixes.get(receiver),
            ))
        decorators.sort(key=lambda item: item[0])

        for start, method, paths, prefix in decorators:
            path = paths[0]
            for candidate in paths:
                full_path = _join_path(prefix, candidate)
                # Flask keeps its methods in the call body; re-read them there.
                methods = [method]
                if method == "GET":
                    # The decorator is `@recv.route(...)`: its call paren is the
                    # first one after the decorator starts.
                    open_idx = text.find("(", start)
                    if open_idx != -1 and open_idx < start + 200:
                        inner, _end = _balanced_call(text, open_idx)
                        methods_match = re.search(r"\bmethods\s*=\s*\[([^\]]*)\]", inner)
                        if methods_match:
                            declared = [
                                m.strip().strip("'\"").upper()
                                for m in methods_match.group(1).split(",")
                            ]
                            declared = [m for m in declared if m in HTTP_METHODS]
                            if declared:
                                methods = declared

                following = RE_PY_VIEW_DEF.search(text, start)
                handler = following.group(1) if following else Path(f).stem
                signature = _python_signature(text, following.start()) if following else ""
                dependencies = _route_dependencies(signature)

                for method_name in methods:
                    key = (method_name, full_path, handler)
                    if key in seen:
                        continue
                    seen.add(key)
                    routes.append({
                        "method": method_name,
                        "path": full_path,
                        "handler": handler,
                        "middleware": dependencies,
                        "framework": "fastapi" if prefix is not None or dependencies else "flask",
                        "evidence": evidence(
                            f, root,
                            find_lines(text, start),
                            make_excerpt(text, start, start + 90),
                        ),
                    })
    return routes


def _view_methods(files: List[Path]) -> Dict[str, List[str]]:
    """Map a Django view function name to the HTTP methods it accepts.

    The methods live in the decorators (`@require_http_methods(["POST"])`),
    not in the URLconf, so they are read once and looked up per URL entry.
    """
    methods: Dict[str, List[str]] = {}
    for f in files:
        if f.suffix.lower() not in PY_EXTS:
            continue
        text = read_text(f)
        for match in RE_PY_VIEW_DEF.finditer(text):
            name = match.group(1)
            preceding = text[max(0, match.start() - 400):match.start()]
            declared = _methods_from_decorators(preceding)
            if declared and name not in methods:
                methods[name] = declared
    return methods


def _resolve_django_module(root: Path, dotted: str, files: List[Path]) -> Optional[Path]:
    """Resolve a module specifier from `include("blog.auth_urls")` to a file."""
    suffix = dotted.replace(".", "/") + ".py"
    for path in files:
        if path.suffix.lower() not in PY_EXTS:
            continue
        rel = path.relative_to(root).as_posix()
        if rel == suffix or rel.endswith("/" + suffix):
            return path
    return None


def _django_url_entries(text: str) -> List[Tuple[int, str, str]]:
    """Return (line, pattern, target-expression) for each URL entry in a file."""
    entries: List[Tuple[int, str, str]] = []
    for match in RE_DJANGO_PATH_CALL.finditer(text):
        open_idx = text.find("(", match.start())
        if open_idx == -1:
            continue
        inner, _end = _balanced_call(text, open_idx)
        args = _split_args(inner)
        if len(args) < 2:
            continue
        pattern = _string_literal(args[0])
        if pattern is None:
            continue  # e.g. `path(module.route_name, ...)`: not a literal we trust
        entries.append((find_lines(text, match.start()), pattern, args[1]))
    return entries


def _collect_viewsets(root: Path, files: List[Path]) -> Dict[str, Dict[str, Any]]:
    """Index DRF viewsets by class name: the actions and permissions they serve.

    A viewset is defined in `views.py` but registered in `urls.py`, so the two
    facts have to be joined across files -- otherwise every route looks like a
    pair of plain GETs and nothing is marked protected.
    """
    viewsets: Dict[str, Dict[str, Any]] = {}
    for f in files:
        if should_skip(f, root) or f.suffix.lower() not in PY_EXTS:
            continue
        text = read_text(f)
        for match in RE_CLASS_VIEWSET.finditer(text):
            name, bases = match.group(1), match.group(2)
            actions = None
            for base_cls, declared in VIEWSET_ACTIONS.items():
                if base_cls in bases:
                    actions = declared
                    break
            if actions is None:
                continue
            body = text[match.end():match.end() + 2000]
            permissions: List[str] = []
            perms_match = re.search(r"permission_classes\s*=\s*\[([^\]]*)\]", body)
            if perms_match:
                permissions = [
                    n.split(".")[-1].strip()
                    for n in perms_match.group(1).split(",")
                ]
                permissions = [n for n in permissions if n and n != "AllowAny"]
            viewsets[name] = {"actions": actions, "permissions": permissions}
    return viewsets


DEFAULT_VIEWSET_ACTIONS = [("GET", "list", ""), ("GET", "retrieve", "/{id}")]


def detect_django_routes(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    """Django URLconf routes and DRF router registrations.

    Django URLs are composed by `include(...)`, so a path is only complete when
    the include chain is walked: `path("api/auth/", include("blog.auth_urls"))`
    plus `path("register", views.register)` is `/api/auth/register`. DRF routes
    are registered on a router instead and take their prefix from the `include`
    of `router.urls` -- a router included that way is not emitted a second time
    without its prefix.
    """
    routes: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str]] = set()
    view_methods = _view_methods(files)
    viewsets = _collect_viewsets(root, files)
    included_routers: Set[Tuple[Path, str]] = set()

    urlconf_files: Dict[Path, List[Tuple[int, str, str]]] = {}
    for f in files:
        if should_skip(f, root) or f.suffix.lower() not in PY_EXTS:
            continue
        text = read_text(f)
        if "urlpatterns" not in text:
            continue
        entries = _django_url_entries(text)
        if entries:
            urlconf_files[f] = entries
    if not urlconf_files:
        return routes

    def add(method: str, path: str, handler: str, file: Path, line: int,
            excerpt: str, middleware: Optional[List[str]] = None) -> None:
        key = (method, path, handler)
        if key in seen:
            return
        seen.add(key)
        routes.append({
            "method": method,
            "path": path,
            "handler": handler,
            "middleware": middleware or [],
            "framework": "django",
            "evidence": evidence(file, root, line, excerpt),
        })

    def add_router(file: Path, prefix: str, text: str, router_var: str) -> None:
        for reg in RE_DRF_REGISTER.finditer(text):
            if reg.group(1) != router_var:
                continue
            registered = reg.group(2) or reg.group(3) or ""
            viewset = reg.group(4).split(".")[-1]
            info = viewsets.get(viewset, {})
            actions = info.get("actions") or DEFAULT_VIEWSET_ACTIONS
            permissions = info.get("permissions") or []
            base = _join_path(prefix, registered)
            for method, action, suffix in actions:
                add(method, base + suffix, "%s.%s" % (viewset, action),
                    file, find_lines(text, reg.start()),
                    make_excerpt(text, reg.start(), reg.end() + 20),
                    permissions)

    def walk(file: Path, prefix: str, depth: int = 0) -> None:
        if depth > 5:  # an include cycle is a real thing in old projects
            return
        text = read_text(file)
        for line, pattern, target in urlconf_files.get(file, []):
            if re.match(r"include\s*\(", target):
                body = target[target.find("(") + 1:target.rfind(")")]
                inner_arg = _split_args(body)[0] if body else ""
                module = _string_literal(inner_arg)
                if module:
                    child = _resolve_django_module(root, module, files)
                    if child is not None:
                        walk(child, _join_path(prefix, pattern), depth + 1)
                    continue
                # include(router.urls): the router's routes start at this prefix.
                router_var = inner_arg.split(".")[0].strip()
                included_routers.add((file, router_var))
                add_router(file, _join_path(prefix, pattern), text, router_var)
                continue

            if target.startswith("admin."):
                continue  # the Django admin is framework code, not this project's

            view_name = target.split(".")[-1].strip()
            methods = view_methods.get(view_name) or ["GET"]
            excerpt_start = read_text(file).find(target)
            excerpt = make_excerpt(text, max(excerpt_start, 0), max(excerpt_start, 0) + 60)
            for method in methods:
                add(method, _join_path(prefix, pattern), target.strip(),
                    file, line, excerpt)

    # Roots: URLconfs that no other module includes.
    included_modules: Set[str] = set()
    for file in urlconf_files:
        text = read_text(file)
        for match in re.finditer(r"include\s*\(\s*['\"]([\w.]+)['\"]", text):
            included_modules.add(match.group(1))

    for file in sorted(urlconf_files):
        rel = file.relative_to(root).as_posix()
        module = rel[:-3].replace("/", ".") if rel.endswith(".py") else rel
        if module in included_modules or module.endswith(".__init__"):
            continue
        walk(file, "")
        # Routers in this file that nothing included still serve their routes,
        # just without a prefix.
        text = read_text(file)
        for router_match in RE_DRF_ROUTER_VAR.finditer(text):
            router_var = router_match.group(1)
            if (file, router_var) in included_routers:
                continue
            add_router(file, "", text, router_var)

    return routes


# ----------------------------------------------------------------------
# Next.js file-based routes
# ----------------------------------------------------------------------

RE_NEXT_EXPORT_METHOD = re.compile(
    r"export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b"
    r"|export\s+const\s+(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s*="
)
RE_NEXT_REQ_METHOD = re.compile(
    r"req\.method\s*===?\s*['\"](GET|POST|PUT|PATCH|DELETE)['\"]"
)


def _nextjs_path(rel_parts: Tuple[str, ...]) -> Optional[str]:
    """Turn a Next.js route file path into the URL it serves."""
    parts = list(rel_parts)
    filename = parts[-1]
    stem, _, _ext = filename.rpartition(".")
    if not stem:
        return None

    if "app" in parts:
        app_idx = len(parts) - 1 - list(reversed(parts)).index("app")
        if stem != "route":
            return None  # a page, not an API route
        segments = parts[app_idx + 1:-1]
    elif "pages" in parts:
        pages_idx = len(parts) - 1 - list(reversed(parts)).index("pages")
        segments = parts[pages_idx + 1:-1]
        if not segments or segments[0] != "api":
            return None
        if stem != "index":
            segments = segments + [stem]
    else:
        return None

    cleaned = []
    for segment in segments:
        if segment.startswith("[[...") or segment.startswith("[..."):
            cleaned.append("{" + segment.strip("[]").lstrip(".") + "}")
        elif segment.startswith("[") and segment.endswith("]"):
            cleaned.append("{" + segment[1:-1] + "}")
        else:
            cleaned.append(segment)
    return "/" + "/".join(cleaned)


def detect_nextjs_routes(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    """Next.js API routes, which are files rather than declarations.

    App Router files (`app/api/x/route.ts`) export one function per method.
    Pages Router files (`pages/api/x.ts`) export one handler and branch on
    `req.method`, so the methods are read from those comparisons.
    """
    routes: List[Dict[str, Any]] = []
    for f in files:
        if should_skip(f, root) or f.suffix.lower() not in JS_EXTS:
            continue
        rel_parts = f.relative_to(root).parts
        path = _nextjs_path(rel_parts)
        if not path:
            continue
        text = read_text(f)
        if not text:
            continue

        declared: List[Tuple[str, int]] = []
        for match in RE_NEXT_EXPORT_METHOD.finditer(text):
            method = match.group(1) or match.group(2)
            declared.append((method, find_lines(text, match.start())))
        if not declared:
            for match in RE_NEXT_REQ_METHOD.finditer(text):
                declared.append((match.group(1), find_lines(text, match.start())))
        if not declared:
            declared.append(("GET", 1))

        app_router = "app" in rel_parts
        seen_methods: Set[str] = set()
        for method, line in declared:
            if method in seen_methods:
                continue
            seen_methods.add(method)
            routes.append({
                "method": method,
                "path": path,
                # App Router files export one function per method, so the
                # export name IS the handler. A Pages Router file exports one
                # default handler that branches on req.method.
                "handler": method if app_router else "handler",
                "middleware": [],
                "framework": "nextjs",
                "evidence": evidence(f, root, line, "%s -> %s %s" % (f.name, method, path)),
            })
    return routes


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------


def detect_test_edges(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    """Match test files to the source file they exercise, by naming convention.

    Conventions covered: `x.test.js`, `x.spec.ts`, `test_x.py`, `x_test.py`.
    Matching is by file stem, which is how the overwhelming majority of
    projects name tests; anything more clever needs a parser we do not have.
    """
    def is_test(path: Path) -> bool:
        name = path.name.lower()
        return (
            ".test." in name or ".spec." in name
            or name.startswith("test_") or name.endswith("_test.py")
        )

    def stem_of(path: Path) -> str:
        name = path.name
        for marker in (".test.", ".spec."):
            if marker in name.lower():
                return name[: name.lower().index(marker)]
        if name.startswith("test_"):
            return path.stem[len("test_"):]
        if name.endswith("_test.py"):
            return path.stem[: -len("_test")]
        return path.stem

    sources = {}
    for path in files:
        if not is_test(path):
            sources.setdefault(path.stem, []).append(path)

    edges = []
    for path in files:
        if not is_test(path):
            continue
        stem = stem_of(path)
        for source in sources.get(stem, []):
            edges.append({
                "source": str(source.relative_to(root)),
                "test": str(path.relative_to(root)),
                "evidence": evidence(path, root, 1, path.name),
            })
    return edges


def detect_all(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    ignore_patterns = load_ignore_patterns(root)
    # Walk once with the shared filter so the detector and the scanner agree on
    # which files belong to the project (no node_modules, build output or .git).
    files = [p for p in walk_files(root, ignore_patterns) if is_source_file(p)]

    return {
        "repo_root": str(root),
        "files_scanned": len(files),
        "express": {
            "routes": detect_express_routes(root, files),
            "middleware": detect_express_middleware(root, files),
        },
        "python": {
            "routes": (
                detect_python_decorator_routes(root, files)
                + detect_django_routes(root, files)
            ),
        },
        "nextjs": {
            "routes": detect_nextjs_routes(root, files),
        },
        "mongoose": {
            "models": detect_mongoose_models(root, files),
        },
        "python_orm": {
            "models": detect_python_orm_models(root, files),
        },
        "react": {
            "components": detect_react_components(root, files),
            "hooks": detect_react_hooks(root, files),
        },
        "api_calls": detect_api_calls(root, files),
        "auth": detect_auth_signals(root, files),
        "imports": detect_imports(root, files),
        "tests": detect_test_edges(root, files),
    }


def main():
    if len(sys.argv) < 2:
        repo_root = Path.cwd()
    else:
        repo_root = Path(sys.argv[1]).resolve()

    if not repo_root.exists():
        print(f"Error: {repo_root} does not exist", file=sys.stderr)
        sys.exit(1)

    print(f"Detecting code facts in {repo_root}...")
    facts = detect_all(repo_root)

    output_dir = repo_root / ".project-defense"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "code-facts.json"
    output_file.write_text(json.dumps(facts, indent=2))
    print(f"Written to {output_file}")

    # Summary
    print()
    print(f"Files scanned:   {facts['files_scanned']}")
    print(f"Express routes:  {len(facts['express']['routes'])}")
    print(f"Express mw:      {len(facts['express']['middleware'])}")
    print(f"Python routes:   {len(facts['python']['routes'])}")
    print(f"Next.js routes:  {len(facts['nextjs']['routes'])}")
    print(f"Mongoose models: {len(facts['mongoose']['models'])}")
    print(f"React components:{len(facts['react']['components'])}")
    print(f"React hooks:     {len(facts['react']['hooks'])}")
    print(f"API calls:       {len(facts['api_calls'])}")
    print(f"JWT.verify:      {len(facts['auth']['jwt_verify'])}")
    print(f"bcrypt calls:    {len(facts['auth']['bcrypt_usage'])}")


if __name__ == "__main__":
    main()