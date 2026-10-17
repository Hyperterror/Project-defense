#!/usr/bin/env python3
"""
detect_code_facts.py -- Stack-specific code detectors for project-defense-skill.

Reads .project-defense/scan-facts.json (or scans a repo), then extracts:
  - Express routes (router.METHOD(path, ...), app.METHOD(...))
  - Express middleware (app.use(...), router.use(...))
  - React components (default exports of functions/arrows, function declarations)
  - React hooks (custom hooks from src/hooks/)
  - Mongoose models (mongoose.model(name, schema))
  - API calls from frontend (axios.get/post, fetch(url, {method}))
  - Authentication signals (JWT verify, bcrypt, password hashing)
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


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def should_skip(path: Path, root: Path) -> bool:
    """Skip files in noise/dependency/secret directories."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    parts = rel.parts
    for p in parts[:-1]:  # check parent dirs
        if p in SKIP_DIRS or p.startswith("."):
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
    """Find authentication-related code patterns."""
    result: Dict[str, Any] = {
        "jwt_verify": [],
        "bcrypt_usage": [],
        "password_handling": [],
    }
    for f in files:
        if should_skip(f, root):
            continue
        if f.suffix.lower() not in JS_EXTS:
            continue
        text = read_text(f)
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
# Main
# ----------------------------------------------------------------------


def detect_all(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    files = [p for p in root.rglob("*") if p.is_file() and is_source_file(p)]

    return {
        "repo_root": str(root),
        "files_scanned": len(files),
        "express": {
            "routes": detect_express_routes(root, files),
            "middleware": detect_express_middleware(root, files),
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
    print(f"Mongoose models: {len(facts['mongoose']['models'])}")
    print(f"React components:{len(facts['react']['components'])}")
    print(f"React hooks:     {len(facts['react']['hooks'])}")
    print(f"API calls:       {len(facts['api_calls'])}")
    print(f"JWT.verify:      {len(facts['auth']['jwt_verify'])}")
    print(f"bcrypt calls:    {len(facts['auth']['bcrypt_usage'])}")


if __name__ == "__main__":
    main()