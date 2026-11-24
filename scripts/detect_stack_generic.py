#!/usr/bin/env python3
"""
detect_stack_generic.py -- Route, model and auth detection for stacks that do not
have a dedicated detector.

The dedicated detectors in `detect_code_facts.py` (Express, Next.js, FastAPI,
Flask, Django) understand a framework's routing model. This module takes the
other approach: a table of patterns, one pack per ecosystem, applied to the files
whose extension belongs to that ecosystem.

What it will never do is invent a route. Every hit needs a literal file, a line
number and the excerpt that matched, exactly like the dedicated detectors, so a
wrong guess is visible in the graph and can be corrected in Phase 4 rather than
silently shaping the interview. When a pack matches nothing, the caller records
an uncertainty instead of pretending the project has no routes.

Supported packs: Go (gin/echo/chi/fiber/net-http), Ruby (Rails, Sinatra),
PHP (Laravel, Slim), Java (Spring), C# (ASP.NET controllers and minimal APIs),
Rust (Axum, Actix), Kotlin (Ktor), Elixir (Phoenix), plus model detection for Go
structs, Rails/Eloquent/JPA entities, Prisma and Ecto schemas.

Stdlib only, Python 3.8+.
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ----------------------------------------------------------------------
# Language tables
# ----------------------------------------------------------------------

# Extension -> ecosystem. Deliberately small: only ecosystems that have a pack
# below, because listing a language we cannot read would produce an empty graph
# that looks like a project with no routes.
EXT_TO_ECOSYSTEM = {
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".rs": "rust",
    ".cs": "csharp",
    ".ex": "elixir",
    ".exs": "elixir",
    ".prisma": "prisma",
}

# Files whose *name* carries the routes rather than whose extension does.
ROUTE_FILE_HINTS = {
    "routes.rb": "ruby",
    "web.php": "php",
    "api.php": "php",
    "routes.php": "php",
    "router.ex": "elixir",
}

HTTP_VERBS = ("GET", "POST", "PUT", "PATCH", "DELETE")

# Rails/Laravel resource expansion: the seven RESTful endpoints of a resource.
RESOURCE_ACTIONS = [
    ("GET", "", "index"),
    ("POST", "", "store"),
    ("GET", "/:id", "show"),
    ("PUT", "/:id", "update"),
    ("PATCH", "/:id", "update"),
    ("DELETE", "/:id", "destroy"),
]
# Laravel's apiResource drops the two HTML form endpoints.
API_RESOURCE_ACTIONS = [
    ("GET", "", "index"),
    ("POST", "", "store"),
    ("GET", "/{id}", "show"),
    ("PUT", "/{id}", "update"),
    ("DELETE", "/{id}", "destroy"),
]


def _evidence(path: Path, root: Path, line_no: int, excerpt: str) -> Dict[str, Any]:
    """The one shape every detection must carry: where it came from."""
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.as_posix()
    return {
        "file": rel,
        "lines": [line_no, line_no],
        "excerpt": excerpt.strip()[:200],
        "status": "code-verified",
    }


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _route(method: str, path: str, handler: str, evidence: Dict[str, Any],
           framework: str, middleware: Optional[List[str]] = None) -> Dict[str, Any]:
    route = {
        "method": method.upper(),
        "path": path,
        "handler": handler,
        "framework": framework,
        "evidence": evidence,
    }
    if middleware:
        route["middleware"] = middleware
    return route


# ----------------------------------------------------------------------
# Route packs
# ----------------------------------------------------------------------

# (name, compiled regex, method group, path group, handler group, default method)
GO_PATTERNS = [
    # gin / echo / chi / fiber: r.GET("/x", handler) -- echo and fiber use .Get
    ("go-router", re.compile(
        r"\b(\w+)\.(GET|POST|PUT|PATCH|DELETE|Get|Post|Put|Patch|Delete)\(\s*\"([^\"]+)\"\s*,\s*([\w.]+|[\w.]+\.\w+)"
    ), 2, 3, 4, None),
    # net/http: http.HandleFunc("/x", handler)
    ("net-http", re.compile(r"http\.HandleFunc\(\s*\"([^\"]+)\"\s*,\s*([\w.]+)"), None, 1, 2, "ANY"),
    # chi: r.Method("GET", "/x", handler)
    ("chi-method", re.compile(r"\.Method\(\s*\"([A-Z]+)\"\s*,\s*\"([^\"]+)\"\s*,\s*([\w.]+)"), 1, 2, 3, None),
]


GO_GROUP = re.compile(r"(\w+)\s*:?=\s*(\w+)\.Group\(\s*\"([^\"]+)\"\s*\)")


def detect_go_routes(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    routes = []
    for path in files:
        if path.suffix.lower() != ".go" or _is_test_file(path):
            continue
        text = _read(path)
        # `api := r.Group("/api")` moves every route on that variable under the
        # prefix. Without this the graph claims GET /notes for GET /api/notes and
        # every later question names a path that does not exist.
        prefixes: Dict[str, str] = {}
        for group in GO_GROUP.finditer(text):
            prefixes[group.group(1)] = group.group(3)
            prefixes[group.group(2)] = group.group(2) and prefixes.get(group.group(2), "")
        for framework, pattern, m_grp, p_grp, h_grp, fixed in GO_PATTERNS:
            for match in pattern.finditer(text):
                verb = fixed or match.group(m_grp).upper()
                receiver = match.group(1) if framework == "go-router" else ""
                prefix = prefixes.get(receiver, "")
                routes.append(_route(
                    verb,
                    _join_paths(prefix, match.group(p_grp)) if prefix else match.group(p_grp),
                    match.group(h_grp),
                    _evidence(path, root, _line_of(text, match.start()), match.group(0)),
                    framework,
                ))
    return routes


RUBY_PATTERNS = [
    # routes.rb: get "/posts", to: "posts#index"
    ("rails", re.compile(
        r"^\s*(get|post|put|patch|delete)\s+[\"']([^\"']+)[\"']\s*(?:,|=>)?\s*(?:to:\s*)?[\"']?(\w+#\w+)?",
        re.MULTILINE,
    )),
    # Sinatra: get "/x" do ... end
    ("sinatra", re.compile(r"^\s*(get|post|put|patch|delete)\s+[\"']([^\"']+)[\"']\s+do\b", re.MULTILINE)),
]
RUBY_RESOURCE = re.compile(r"^\s*resources?\s+:(\w+)(?:,\s*only:\s*\[([^\]]*)\])?", re.MULTILINE)


def detect_ruby_routes(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    routes = []
    for path in files:
        name = path.name.lower()
        if path.suffix.lower() != ".rb" and name != "routes.rb":
            continue
        text = _read(path)
        namespaces = _ruby_namespaces(text)

        def prefixed(target: str, offset: int) -> str:
            base = _ruby_path(target)
            # Nested namespaces compose: namespace :api { namespace :v1 } -> /api/v1
            active = sorted(
                (start, prefix) for start, end, prefix in namespaces if start <= offset < end
            )
            for _, prefix in active:
                base = _join_paths(prefix, base)
            return base

        for framework, pattern in RUBY_PATTERNS:
            for match in pattern.finditer(text):
                verb = match.group(1).upper()
                target = match.group(2)
                handler = (
                    match.group(3) if match.re.groups >= 3 and match.group(3) else None
                ) or f"{target} handler"
                routes.append(_route(
                    verb, prefixed(target, match.start()), handler,
                    _evidence(path, root, _line_of(text, match.start()), match.group(0)),
                    framework,
                ))
        # `resources :posts` is seven endpoints, the same way a DRF viewset is:
        # expand it so the interview can ask about the real surface.
        for match in RUBY_RESOURCE.finditer(text):
            resource = match.group(1)
            only = match.group(2)
            allowed = {a.strip().strip(":").replace(":", "") for a in only.split(",")} if only else None
            for verb, suffix, action in RESOURCE_ACTIONS:
                if allowed and action not in allowed and not (
                    action == "store" and "create" in allowed
                ) and not (action == "destroy" and "destroy" in allowed):
                    continue
                routes.append(_route(
                    verb, prefixed(f"/{resource}{suffix}", match.start()),
                    f"{resource.capitalize()}Controller#{action}",
                    _evidence(path, root, _line_of(text, match.start()), match.group(0)),
                    "rails",
                ))
    return routes


def _ruby_path(target: str) -> str:
    """Rails route targets are relative; make them look like paths."""
    if target.startswith("/"):
        return target
    return "/" + target


PHP_PATTERNS = [
    # Laravel: Route::get('/x', [Controller::class, 'method'])
    ("laravel", re.compile(
        r"Route::(get|post|put|patch|delete|any)\(\s*['\"]([^'\"]+)['\"]\s*,\s*(\[[^\]]*\]|['\"][\w.@]+['\"]|[\w\\]+::class)"
    )),
    # Slim: $app->get('/x', handler)
    ("slim", re.compile(r"\$app->(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]\s*,\s*([^)]*)")),
]
PHP_RESOURCE = re.compile(
    r"Route::(apiResource|resource)\(\s*['\"]([^'\"]+)['\"]\s*,\s*([\w\\]+)::class"
)


PHP_PREFIX = re.compile(r"Route::prefix\(\s*['\"]([^'\"]+)['\"]\s*\)")


def _php_prefix_ranges(text: str) -> List[Tuple[int, int, str]]:
    """Ranges covered by `Route::prefix('api')->group(function () { ... })`."""
    ranges = []
    for match in PHP_PREFIX.finditer(text):
        brace = text.find("{", match.end())
        if brace == -1:
            continue
        depth, end = 0, len(text)
        for index in range(brace, len(text)):
            char = text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index
                    break
        ranges.append((match.start(), end, match.group(1)))
    return sorted(ranges, key=lambda item: item[1] - item[0])


def detect_php_routes(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    routes = []
    for path in files:
        if path.suffix.lower() != ".php":
            continue
        text = _read(path)
        prefixes = _php_prefix_ranges(text)

        def prefixed(target: str, offset: int) -> str:
            base = target if target.startswith("/") else "/" + target
            active = sorted(
                (start, prefix) for start, end, prefix in prefixes if start <= offset < end
            )
            for _, prefix in active:
                base = _join_paths(prefix, base)
            return base

        for framework, pattern in PHP_PATTERNS:
            for match in pattern.finditer(text):
                verb = "ANY" if match.group(1).lower() == "any" else match.group(1).upper()
                handlers = [g for g in match.groups()[2:] if g]
                handler = _php_handler(handlers[0] if handlers else "")
                middleware = _php_middleware(text, match)
                routes.append(_route(
                    verb, prefixed(match.group(2), match.start()), handler,
                    _evidence(path, root, _line_of(text, match.start()), match.group(0)),
                    framework, middleware,
                ))
        for match in PHP_RESOURCE.finditer(text):
            kind, resource, controller = match.group(1), match.group(2), match.group(3)
            actions = API_RESOURCE_ACTIONS if kind == "apiResource" else RESOURCE_ACTIONS
            for verb, suffix, action in actions:
                routes.append(_route(
                    verb, prefixed(f"/{resource}{suffix}", match.start()), f"{controller}@{action}",
                    _evidence(path, root, _line_of(text, match.start()), match.group(0)),
                    "laravel",
                ))
    return routes


def _php_handler(raw: str) -> str:
    cleaned = raw.strip().strip("[]")
    parts = [p.strip().strip("'\"") for p in re.split(r",", cleaned) if p.strip()]
    if len(parts) >= 2:
        return f"{parts[0]}@{parts[1]}"
    return parts[0] if parts else "closure"


def _php_middleware(text: str, match: "re.Match") -> List[str]:
    """A route-level `->middleware('auth')` on the same statement.

    The statement ends at its semicolon: scanning a fixed window instead made a
    guarded route protect the route on the following line.
    """
    end = text.find(";", match.end())
    tail = text[match.end(): end if end != -1 else match.end() + 200]
    found = re.search(r"->middleware\(\s*\[?['\"]([\w:.-]+)", tail)
    return [found.group(1)] if found else []


JAVA_CLASS_MAP = re.compile(r"@RequestMapping\(\s*(?:value\s*=\s*)?\{?\"([^\"]*)\"")
JAVA_METHOD_MAP = re.compile(
    r"@(Get|Post|Put|Patch|Delete)Mapping\(\s*(?:value\s*=\s*)?\{?\"?([^\")]*)\"?\)?"
)
JAVA_REQUEST_MAP = re.compile(
    r"@RequestMapping\(\s*(?:value\s*=\s*)?\{?\"([^\"]*)\"\{?[^)]*?method\s*=\s*RequestMethod\.(\w+)"
)
JAVA_HANDLER = re.compile(r"(?:public|protected)\s+[\w<>\[\], .]+\s+(\w+)\s*\(")


def detect_java_routes(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    routes = []
    for path in files:
        if path.suffix.lower() != ".java":
            continue
        text = _read(path)
        class_prefix = ""
        class_match = JAVA_CLASS_MAP.search(text)
        if class_match:
            class_prefix = class_match.group(1)

        guard_on_class = "@PreAuthorize" in text.split("class ")[0] if "class " in text else False

        for match in JAVA_METHOD_MAP.finditer(text):
            verb = match.group(1).upper()
            suffix = match.group(2) or ""
            handler_match = JAVA_HANDLER.search(text, match.end())
            handler = handler_match.group(1) if handler_match else "handler"
            guard = ["@PreAuthorize"] if ("@PreAuthorize" in text[max(0, match.start() - 200):match.start()] or guard_on_class) else None
            routes.append(_route(
                verb, _join_paths(class_prefix, suffix), handler,
                _evidence(path, root, _line_of(text, match.start()), match.group(0)),
                "spring", guard,
            ))
        for match in JAVA_REQUEST_MAP.finditer(text):
            handler_match = JAVA_HANDLER.search(text, match.end())
            routes.append(_route(
                match.group(2).upper(), _join_paths(class_prefix, match.group(1)),
                handler_match.group(1) if handler_match else "handler",
                _evidence(path, root, _line_of(text, match.start()), match.group(0)),
                "spring",
            ))
    return routes


CSHARP_CLASS_ROUTE = re.compile(r"\[Route\(\s*\"([^\"]+)\"\s*\)\]")
CSHARP_METHOD_ROUTE = re.compile(r"\[Http(Get|Post|Put|Patch|Delete)(?:\(\s*\"([^\"]*)\"\s*\))?\]")
CSHARP_MINIMAL = re.compile(
    r"app\.Map(Get|Post|Put|Patch|Delete)\(\s*\"([^\"]+)\"\s*(?:,\s*([\w.]+))?"
)
CSHARP_HANDLER = re.compile(r"public\s+(?:async\s+)?[\w<>\[\], .]+\s+(\w+)\s*\(")


CSHARP_CLASS_NAME = re.compile(r"public\s+(?:sealed\s+|partial\s+)?class\s+(\w+)")


def detect_csharp_routes(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    routes = []
    for path in files:
        if path.suffix.lower() != ".cs":
            continue
        text = _read(path)
        prefix_match = CSHARP_CLASS_ROUTE.search(text)
        prefix = prefix_match.group(1) if prefix_match else ""
        # [Route("api/[controller]")] is ASP.NET's placeholder for the class
        # name without its Controller suffix; leaving it literal would make
        # every question name a path that does not exist.
        if "[controller]" in prefix.lower():
            class_match = CSHARP_CLASS_NAME.search(text)
            controller = class_match.group(1) if class_match else ""
            if controller.lower().endswith("controller"):
                controller = controller[: -len("controller")]
            prefix = re.sub(r"\[controller\]", controller.lower(), prefix, flags=re.IGNORECASE)
        for match in CSHARP_METHOD_ROUTE.finditer(text):
            handler_match = CSHARP_HANDLER.search(text, match.end())
            guard = ["[Authorize]"] if "[Authorize" in text[max(0, match.start() - 200):match.start()] else None
            routes.append(_route(
                match.group(1).upper(), _join_paths(prefix, match.group(2) or ""),
                handler_match.group(1) if handler_match else "action",
                _evidence(path, root, _line_of(text, match.start()), match.group(0)),
                "aspnet", guard,
            ))
        for match in CSHARP_MINIMAL.finditer(text):
            routes.append(_route(
                match.group(1).upper(), match.group(2),
                match.group(3) or f"Map{match.group(1)} handler",
                _evidence(path, root, _line_of(text, match.start()), match.group(0)),
                "aspnet-minimal",
            ))
    return routes


RUST_AXUM = re.compile(
    r"\.route\(\s*\"([^\"]+)\"\s*,\s*(get|post|put|patch|delete)\(([\w:]+)\)"
)
RUST_ACTIX = re.compile(r"#\[(get|post|put|patch|delete)\(\s*\"([^\"]+)\"\s*\)\]")
RUST_FN = re.compile(r"(?:pub\s+)?async\s+fn\s+(\w+)")


def detect_rust_routes(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    routes = []
    for path in files:
        if path.suffix.lower() != ".rs":
            continue
        text = _read(path)
        for match in RUST_AXUM.finditer(text):
            routes.append(_route(
                match.group(2).upper(), match.group(1), match.group(3),
                _evidence(path, root, _line_of(text, match.start()), match.group(0)),
                "axum",
            ))
        for match in RUST_ACTIX.finditer(text):
            fn_match = RUST_FN.search(text, match.end())
            routes.append(_route(
                match.group(1).upper(), match.group(2),
                fn_match.group(1) if fn_match else "handler",
                _evidence(path, root, _line_of(text, match.start()), match.group(0)),
                "actix",
            ))
    return routes


KOTLIN_KTOR = re.compile(r"\b(get|post|put|patch|delete)\(\s*\"([^\"]+)\"\s*\)\s*\{")


def detect_kotlin_routes(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    routes = []
    for path in files:
        if path.suffix.lower() not in (".kt", ".kts"):
            continue
        text = _read(path)
        for match in KOTLIN_KTOR.finditer(text):
            routes.append(_route(
                match.group(1).upper(), match.group(2), f"route {match.group(2)}",
                _evidence(path, root, _line_of(text, match.start()), match.group(0)),
                "ktor",
            ))
    return routes


ELIXIR_ROUTE = re.compile(
    r"^\s*((?:get|post|put|patch|delete))\s+\"([^\"]+)\"\s*,\s*(\w+)\s*,\s*:(\w+)", re.MULTILINE
)
ELIXIR_RESOURCES = re.compile(r"^\s*resources\s+\"([^\"]+)\"\s*,\s*(\w+)", re.MULTILINE)


def detect_elixir_routes(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    routes = []
    for path in files:
        if path.suffix.lower() not in (".ex", ".exs"):
            continue
        text = _read(path)
        for match in ELIXIR_ROUTE.finditer(text):
            routes.append(_route(
                match.group(1).upper(), match.group(2), f"{match.group(3)}.{match.group(4)}",
                _evidence(path, root, _line_of(text, match.start()), match.group(0)),
                "phoenix",
            ))
        for match in ELIXIR_RESOURCES.finditer(text):
            resource, controller = match.group(1), match.group(2)
            for verb, suffix, action in RESOURCE_ACTIONS:
                routes.append(_route(
                    verb, f"/{resource}{suffix.replace(':id', ':id')}",
                    f"{controller}Controller.{action}",
                    _evidence(path, root, _line_of(text, match.start()), match.group(0)),
                    "phoenix",
                ))
    return routes


ROUTE_DETECTORS = {
    "go": detect_go_routes,
    "ruby": detect_ruby_routes,
    "php": detect_php_routes,
    "java": detect_java_routes,
    "csharp": detect_csharp_routes,
    "rust": detect_rust_routes,
    "kotlin": detect_kotlin_routes,
    "elixir": detect_elixir_routes,
}


def _ruby_namespaces(text: str) -> List[Tuple[int, int, str]]:
    """Ranges covered by `namespace :api do ... end`, outermost first.

    Rails nests namespaces by indentation, so a namespace block ends at the
    first `end` that is no deeper than the `namespace` line itself.
    """
    ranges: List[Tuple[int, int, str]] = []
    pattern = re.compile(r"^(\s*)namespace\s+:(\w+)\s+do\b", re.MULTILINE)
    for match in pattern.finditer(text):
        indent = len(match.group(1))
        closing = re.compile(r"^\s{0,%d}end\b" % indent, re.MULTILINE)
        end_match = closing.search(text, match.end())
        end = end_match.start() if end_match else len(text)
        ranges.append((match.start(), end, match.group(2)))
    # Innermost wins, so sort by span width ascending when applying.
    return sorted(ranges, key=lambda item: item[1] - item[0])


def _join_paths(prefix: str, suffix: str) -> str:
    """'/api/posts' + '/{id}' -> '/api/posts/{id}' (never '//')."""
    left = "/" + (prefix or "").strip("/") if prefix else ""
    right = (suffix or "").strip("/")
    joined = "/".join(part for part in (left.strip("/"), right) if part)
    return "/" + joined


def _is_test_file(path: Path) -> bool:
    lowered = path.name.lower()
    return (
        lowered.endswith("_test.go")
        or lowered.endswith("_test.py")
        or lowered.endswith(".test.ts")
        or lowered.endswith(".spec.ts")
        or lowered.endswith("test.java")
        or "test" in lowered.split(".")[0] and lowered.endswith(".rb")
    )


# ----------------------------------------------------------------------
# Model packs
# ----------------------------------------------------------------------

GO_STRUCT = re.compile(r"type\s+(\w+)\s+struct\s*\{", re.MULTILINE)
GO_FIELD = re.compile(r"^\s*(\w+)\s+([\w\.\[\]\*]+)\s+`[^`]*json:\"(\w+)", re.MULTILINE)
RUBY_MODEL = re.compile(r"class\s+(\w+)\s*<\s*ApplicationRecord")
RUBY_ASSOC = re.compile(r"^\s*(has_many|belongs_to|has_one)\s+:(\w+)", re.MULTILINE)
PHP_MODEL = re.compile(r"class\s+(\w+)\s+extends\s+(?:Model|Authenticatable)")
PHP_FILLABLE = re.compile(r"\$fillable\s*=\s*\[([^\]]*)\]", re.DOTALL)
JAVA_ENTITY = re.compile(r"@Entity[^;]*?class\s+(\w+)", re.DOTALL)
JAVA_COLUMN = re.compile(r"@Column[^;]*?(?:name\s*=\s*\"(\w+)\")?", re.DOTALL)
PRISMA_MODEL = re.compile(r"model\s+(\w+)\s*\{([^}]*)\}", re.DOTALL)
ELIXIR_SCHEMA = re.compile(r'schema\s+"(\w+)"')


def detect_go_models(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    models = []
    for path in files:
        if path.suffix.lower() != ".go" or _is_test_file(path):
            continue
        text = _read(path)
        # A struct is a model when the file is in a models/ package, or the
        # struct carries persistence/serialisation tags.
        looks_like_model = "models" in path.as_posix().lower() or "gorm" in text or "bson:\"" in text
        if not looks_like_model:
            continue
        for match in GO_STRUCT.finditer(text):
            name = match.group(1)
            lowered = name.lower()
            if any(token in lowered for token in (
                "request", "response", "dto", "payload", "params", "config",
                "handler", "input", "output", "result",
            )):
                continue
            body_start = match.end()
            body_end = text.find("\n}", body_start)
            body = text[body_start:body_end if body_end != -1 else len(text)]
            fields = [
                {"name": field.group(3), "type": field.group(2), "required": True}
                for field in GO_FIELD.finditer(body)
            ]
            models.append({
                "name": name,
                "fields": fields,
                "evidence": _evidence(path, root, _line_of(text, match.start()), match.group(0)),
            })
    return models


def detect_ruby_models(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    models = []
    for path in files:
        if path.suffix.lower() != ".rb":
            continue
        text = _read(path)
        for match in RUBY_MODEL.finditer(text):
            body = text[match.end():match.end() + 2000]
            fields = [
                {"name": m.group(2), "type": m.group(1), "required": False}
                for m in RUBY_ASSOC.finditer(body)
            ]
            models.append({
                "name": match.group(1),
                "fields": fields,
                "evidence": _evidence(path, root, _line_of(text, match.start()), match.group(0)),
            })
    return models


def detect_php_models(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    models = []
    for path in files:
        if path.suffix.lower() != ".php":
            continue
        text = _read(path)
        for match in PHP_MODEL.finditer(text):
            fillable = PHP_FILLABLE.search(text)
            fields = []
            if fillable:
                fields = [
                    {"name": f.strip().strip("'\""), "type": "unknown", "required": False}
                    for f in fillable.group(1).split(",")
                    if f.strip()
                ]
            models.append({
                "name": match.group(1),
                "fields": fields,
                "evidence": _evidence(path, root, _line_of(text, match.start()), match.group(0)),
            })
    return models


def detect_java_models(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    models = []
    for path in files:
        if path.suffix.lower() != ".java":
            continue
        text = _read(path)
        for match in JAVA_ENTITY.finditer(text):
            models.append({
                "name": match.group(1),
                "fields": [],
                "evidence": _evidence(path, root, _line_of(text, match.start()), "@Entity"),
                "orm": "jpa",
            })
    return models


def detect_prisma_models(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    models = []
    for path in files:
        if path.suffix.lower() != ".prisma":
            continue
        text = _read(path)
        for match in PRISMA_MODEL.finditer(text):
            fields = []
            for line in match.group(2).splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and not parts[0].startswith("//"):
                    fields.append({
                        "name": parts[0],
                        "type": parts[1].rstrip("?"),
                        "required": "?" not in parts[1] and "@default" not in line,
                    })
            models.append({
                "name": match.group(1),
                "fields": fields,
                "evidence": _evidence(path, root, _line_of(text, match.start()), match.group(0)[:80]),
                "orm": "prisma",
            })
    return models


def detect_elixir_models(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    models = []
    for path in files:
        if path.suffix.lower() not in (".ex", ".exs"):
            continue
        text = _read(path)
        for match in ELIXIR_SCHEMA.finditer(text):
            models.append({
                "name": match.group(1),
                "fields": [],
                "evidence": _evidence(path, root, _line_of(text, match.start()), match.group(0)),
                "orm": "ecto",
            })
    return models


MODEL_DETECTORS = {
    "go": detect_go_models,
    "ruby": detect_ruby_models,
    "php": detect_php_models,
    "java": detect_java_models,
    "prisma": detect_prisma_models,
    "elixir": detect_elixir_models,
}


# ----------------------------------------------------------------------
# Auth signals
# ----------------------------------------------------------------------

# (ecosystem, kind, regex). `kind` decides which graph bucket the signal lands in:
# token -> token issuance/verification, hash -> password hashing,
# guard -> protected-route machinery, permission -> role checks,
# session -> cookie sessions.
AUTH_PATTERNS = [
    ("go", "token", re.compile(r"jwt\.(Parse|NewWithClaims)|jwt-go|golang-jwt|ginjwt|jwtauth")),
    ("go", "hash", re.compile(r"bcrypt\.(GenerateFromPassword|CompareHashAndPassword)|argon2\.|scrypt\.")),
    ("go", "guard", re.compile(r"func\s+AuthMiddleware|JWTMiddleware|RequireAuth|AuthRequired")),
    ("ruby", "token", re.compile(r"\bJWT\.(encode|decode)\b|jwt")),
    ("ruby", "hash", re.compile(r"has_secure_password|BCrypt::Password|bcrypt")),
    ("ruby", "guard", re.compile(r"before_action\s+:authenticate|authenticate_user!|devise")),
    ("php", "token", re.compile(r"JWT::encode|firebase/php-jwt|tymon/jwt-auth")),
    ("php", "api_key", re.compile(r"sanctum|passport|createToken\(")),
    ("php", "hash", re.compile(r"Hash::make|password_hash\(|Hash::check")),
    ("php", "guard", re.compile(r"middleware\(\s*\['?auth|->middleware\('auth|@auth|Auth::user")),
    ("java", "token", re.compile(r"io\.jsonwebtoken|JwtBuilder|Jwts\.(builder|parser)")),
    ("java", "hash", re.compile(r"BCryptPasswordEncoder|PasswordEncoder|Pbkdf2PasswordEncoder")),
    ("java", "permission", re.compile(r"@PreAuthorize|@Secured|@RolesAllowed")),
    ("java", "guard", re.compile(r"SecurityContextHolder|WebSecurityConfigurerAdapter|SecurityFilterChain")),
    ("csharp", "token", re.compile(r"JwtSecurityToken|AddJwtBearer|JwtBearerDefaults")),
    ("csharp", "hash", re.compile(r"PasswordHasher|BCrypt\.Net|HashPassword")),
    ("csharp", "permission", re.compile(r"\[Authorize")),
    ("csharp", "guard", re.compile(r"AddAuthentication|UseAuthentication")),
    ("rust", "token", re.compile(r"jsonwebtoken|decode::<|encode::<")),
    ("rust", "hash", re.compile(r"argon2|bcrypt::|Argon2::")),
    ("rust", "guard", re.compile(r"from_fn\(|middleware::from_fn|AuthLayer")),
    ("kotlin", "token", re.compile(r"\bjwt\b|JWT\.decode|auth-jwt")),
    ("kotlin", "hash", re.compile(r"bcrypt|BCrypt")),
    ("kotlin", "guard", re.compile(r"authenticate\(|AuthenticationFeature")),
    ("elixir", "token", re.compile(r"Phoenix\.Token|Guardian|JOSE")),
    ("elixir", "hash", re.compile(r"Bcrypt|Argon2|Pbkdf2")),
    ("elixir", "guard", re.compile(r"plug\s+EnsureAuthenticated|Pow\.Plug")),
]


def detect_generic_auth(root: Path, files: List[Path]) -> Dict[str, List[Dict[str, Any]]]:
    """Collect auth signals per ecosystem with the file that proves each one."""
    found: Dict[str, List[Dict[str, Any]]] = {}
    for path in files:
        ecosystem = _ecosystem_of(path)
        if not ecosystem:
            continue
        text = _read(path)
        if not text:
            continue
        for pack_eco, kind, pattern in AUTH_PATTERNS:
            if pack_eco != ecosystem:
                continue
            for match in pattern.finditer(text):
                found.setdefault(kind, []).append({
                    "ecosystem": ecosystem,
                    "match": match.group(0)[:80],
                    "evidence": _evidence(path, root, _line_of(text, match.start()), match.group(0)),
                })
                break
    return found


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------


def _ecosystem_of(path: Path) -> Optional[str]:
    lowered = path.name.lower()
    if lowered in ROUTE_FILE_HINTS:
        return ROUTE_FILE_HINTS[lowered]
    return EXT_TO_ECOSYSTEM.get(path.suffix.lower())


def ecosystems_present(files: Iterable[Path]) -> List[str]:
    seen = []
    for path in files:
        eco = _ecosystem_of(path)
        if eco and eco not in seen:
            seen.append(eco)
    return sorted(seen)


RUBY_CONTROLLER_CLASS = re.compile(r"class\s+(\w+Controller)\s*<")
RUBY_GUARD = re.compile(r"^\s*before_action\s+:(authenticate_\w*!?|require_\w*!?|authorize\w*!?)", re.MULTILINE)


def detect_ruby_guards(root: Path, files: List[Path]) -> List[Dict[str, Any]]:
    """Controller-level guards: `before_action :authenticate_user!`.

    Rails protects a whole controller, not a route, so the guard has to be joined
    to the routes by controller name. Without this a Rails app with Devise looks
    like it has no protected endpoints at all.
    """
    guards = []
    for path in files:
        if path.suffix.lower() != ".rb":
            continue
        text = _read(path)
        class_match = RUBY_CONTROLLER_CLASS.search(text)
        if not class_match:
            continue
        controller = class_match.group(1)
        guard_match = RUBY_GUARD.search(text)
        if not guard_match:
            continue
        excepts = re.search(r",\s*except:\s*\[([^\]]*)\]", text)
        guards.append({
            "controller": controller,
            "guard": guard_match.group(1),
            "except": [part.strip().strip(":") for part in excepts.group(1).split(",")] if excepts else [],
            "evidence": _evidence(path, root, _line_of(text, guard_match.start()), guard_match.group(0)),
        })
    return guards


def detect_generic(root: Path, files: List[Path]) -> Dict[str, Any]:
    """Run every applicable pack. Returns routes, models and auth signals."""
    ecosystems = ecosystems_present(files)
    routes: List[Dict[str, Any]] = []
    models: List[Dict[str, Any]] = []
    for eco in ecosystems:
        detector = ROUTE_DETECTORS.get(eco)
        if detector:
            routes.extend(detector(root, files))
        model_detector = MODEL_DETECTORS.get(eco)
        if model_detector:
            models.extend(model_detector(root, files))

    # One route per (method, path): a Rails resource block and an explicit line
    # can describe the same endpoint, and duplicates would become duplicate
    # questions.
    deduped: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for route in routes:
        key = (route["method"], route["path"])
        deduped.setdefault(key, route)

    return {
        "ecosystems": ecosystems,
        "routes": [deduped[key] for key in sorted(deduped)],
        "models": models,
        "auth": detect_generic_auth(root, files),
        "guards": detect_ruby_guards(root, files) if "ruby" in ecosystems else [],
    }
