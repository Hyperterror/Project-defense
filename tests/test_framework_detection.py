#!/usr/bin/env python3
"""
test_framework_detection.py -- Tests for non-Express stack coverage.

The skill used to see only Express: a Django, FastAPI or Next.js project
produced no routes, so the question bank collapsed to a handful of generic
questions. These tests pin the detectors that close that gap, and the two
places the result is consumed (the graph and the question bank).

Covered:
  - FastAPI decorators, router prefixes and `Depends(...)` guards
  - Flask `@app.route(..., methods=[...])`
  - Django `include()` chaining, view decorators, DRF viewset permissions
  - Next.js App Router and Pages Router file routing
  - delegated (cookie) auth detection
  - route merging into one backend list
  - one coding question per resource, not per verb
  - challenge relocation to the file that defines the handler

Run: python3 -m unittest discover -s tests -p "test_*.py"
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import build_graph  # noqa: E402
import detect_code_facts as detect  # noqa: E402
import generate_challenge as gc  # noqa: E402
import generate_question_bank as gqb  # noqa: E402


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _source_files(root):
    return [
        path for path in root.rglob("*")
        if path.is_file() and detect.is_source_file(path)
    ]


def _paths(routes):
    return {(r["method"], r["path"]) for r in routes}


class TempRepo(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-fw-"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestFastApi(TempRepo):
    def _repo(self):
        _write(self.tmpdir, "app/main.py", '''
from fastapi import FastAPI, Depends, APIRouter

app = FastAPI()
router = APIRouter(prefix="/tasks")


def get_current_user():
    ...


@app.post("/auth/login")
def login(payload: dict):
    return {}


@router.get("/{task_id}")
def read_task(task_id: int, user=Depends(get_current_user)):
    return {}


@router.delete("/{task_id}")
def delete_task(
    task_id: int,
    user=Depends(get_current_user),
):
    return {}
''')

    def test_decorator_routes_are_found(self):
        self._repo()
        routes = detect.detect_python_decorator_routes(self.tmpdir, _source_files(self.tmpdir))
        self.assertEqual(
            _paths(routes),
            {("POST", "/auth/login"), ("GET", "/tasks/{task_id}"),
             ("DELETE", "/tasks/{task_id}")},
        )

    def test_router_prefix_and_handler_names(self):
        self._repo()
        routes = detect.detect_python_decorator_routes(self.tmpdir, _source_files(self.tmpdir))
        by_path = {(r["method"], r["path"]): r for r in routes}
        self.assertEqual(by_path[("GET", "/tasks/{task_id}")]["handler"], "read_task")
        # A multi-line signature must still yield its dependency guard.
        self.assertEqual(by_path[("DELETE", "/tasks/{task_id}")]["middleware"], ["get_current_user"])
        self.assertEqual(by_path[("POST", "/auth/login")]["middleware"], [])

    def test_flask_methods_list_expands_to_one_route_each(self):
        _write(self.tmpdir, "service.py", '''
from flask import Flask
app = Flask(__name__)


@app.route("/items", methods=["GET", "POST"])
def items():
    return ""
''')
        routes = detect.detect_python_decorator_routes(self.tmpdir, _source_files(self.tmpdir))
        self.assertEqual(_paths(routes), {("GET", "/items"), ("POST", "/items")})


class TestDjango(TempRepo):
    def _repo(self):
        _write(self.tmpdir, "example_blog/urls.py", '''
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from blog.views import PostViewSet

router = DefaultRouter()
router.register(r"posts", PostViewSet, basename="post")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/auth/", include("blog.auth_urls")),
]
''')
        _write(self.tmpdir, "blog/auth_urls.py", '''
from django.urls import path
from blog import views

urlpatterns = [
    path("register", views.register, name="auth-register"),
]
''')
        _write(self.tmpdir, "blog/views.py", '''
from django.views.decorators.http import require_http_methods
from rest_framework import viewsets, permissions


@require_http_methods(["POST"])
def register(request):
    return None


class PostViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
''')

    def test_include_prefix_is_applied(self):
        self._repo()
        routes = detect.detect_django_routes(self.tmpdir, _source_files(self.tmpdir))
        self.assertIn(("POST", "/api/auth/register"), _paths(routes))

    def test_admin_is_not_a_project_route(self):
        self._repo()
        routes = detect.detect_django_routes(self.tmpdir, _source_files(self.tmpdir))
        self.assertFalse([r for r in routes if r["path"].startswith("/admin")])

    def test_viewset_actions_come_from_the_class_in_another_file(self):
        self._repo()
        routes = detect.detect_django_routes(self.tmpdir, _source_files(self.tmpdir))
        posts = {(r["method"], r["path"]): r for r in routes if "/api/posts" in r["path"]}
        self.assertIn(("POST", "/api/posts"), posts)
        self.assertEqual(posts[("DELETE", "/api/posts/{id}")]["handler"], "PostViewSet.destroy")
        self.assertEqual(posts[("POST", "/api/posts")]["middleware"], ["IsAuthenticated"])

    def test_router_is_not_emitted_twice_without_its_prefix(self):
        self._repo()
        routes = detect.detect_django_routes(self.tmpdir, _source_files(self.tmpdir))
        self.assertFalse([r for r in routes if r["path"].startswith("/posts")])


class TestNextJs(TempRepo):
    def test_app_router_methods_and_dynamic_segments(self):
        _write(self.tmpdir, "app/api/todos/route.ts", '''
export async function GET(request: NextRequest) {
  return NextResponse.json([]);
}

export async function POST(request: NextRequest) {
  return NextResponse.json({}, { status: 201 });
}
''')
        _write(self.tmpdir, "app/api/todos/[id]/route.ts", '''
export async function PATCH(request: NextRequest) {
  return NextResponse.json({});
}
''')
        _write(self.tmpdir, "app/page.tsx", "export default function Page() { return null; }\n")
        routes = detect.detect_nextjs_routes(self.tmpdir, _source_files(self.tmpdir))
        self.assertEqual(
            _paths(routes),
            {("GET", "/api/todos"), ("POST", "/api/todos"), ("PATCH", "/api/todos/{id}")},
        )

    def test_pages_router_reads_method_branches(self):
        _write(self.tmpdir, "pages/api/items.ts", '''
export default function handler(req, res) {
  if (req.method === 'POST') {
    return res.status(201).json({});
  }
  return res.json([]);
}
''')
        routes = detect.detect_nextjs_routes(self.tmpdir, _source_files(self.tmpdir))
        self.assertEqual(_paths(routes), {("POST", "/api/items")})


class TestAuthStrategies(TempRepo):
    def test_python_jwt_is_detected(self):
        _write(self.tmpdir, "app/main.py", "import jwt\n\n\ndef verify(token):\n    return jwt.decode(token, 'k', algorithms=['HS256'])\n")
        facts = detect.detect_all(self.tmpdir)
        code = {"auth": facts["auth"], "express": {}, "python": facts["python"], "nextjs": facts["nextjs"]}
        auth = build_graph.build_auth(code, [])
        self.assertEqual(auth["strategy"], "JWT")

    def test_delegated_provider_auth_is_a_cookie_session(self):
        _write(self.tmpdir, "lib/auth.ts", '''
import { createServerClient } from "@supabase/ssr";

export function client() {
  return createServerClient(url, key, { cookies: {} });
}
''')
        facts = detect.detect_all(self.tmpdir)
        code = {"auth": facts["auth"], "express": {}, "python": facts["python"], "nextjs": facts["nextjs"]}
        auth = build_graph.build_auth(code, [])
        self.assertEqual(auth["strategy"], "cookie")
        self.assertIn("auth.ts", auth["token_handling"].replace("\\", "/"))


class TestGraphMergesFrameworks(TempRepo):
    def test_all_frameworks_land_in_one_backend_route_list(self):
        code = {
            "express": {"routes": [], "middleware": []},
            "python": {"routes": [
                {"method": "GET", "path": "/tasks", "handler": "list_tasks",
                 "middleware": ["get_current_user"],
                 "evidence": {"file": "app/main.py", "lines": [1, 1],
                              "excerpt": "x", "status": "code-verified"}},
            ]},
            "nextjs": {"routes": [
                {"method": "POST", "path": "/api/todos", "handler": "POST",
                 "middleware": [],
                 "evidence": {"file": "app/api/todos/route.ts", "lines": [1, 1],
                              "excerpt": "x", "status": "code-verified"}},
            ]},
        }
        backend = build_graph.build_backend(code)
        self.assertEqual(len(backend["routes"]), 2)
        guarded = [r for r in backend["routes"] if r["handler"] == "list_tasks"][0]
        self.assertEqual(guarded["middleware"], ["get_current_user"])

        auth = build_graph.build_auth(code, backend["routes"])
        self.assertIn("GET /tasks", [r["name"] for r in auth["protected_routes"]])


class TestCodingQuestionGrouping(unittest.TestCase):
    def _graph(self):
        def route(method, path, handler):
            return {
                "method": method, "path": path, "handler": handler,
                "evidence": {"file": "api/views.py", "lines": [1, 1],
                             "excerpt": "x", "status": "code-verified"},
            }
        return {
            "backend": {"routes": [
                route("GET", "/api/posts", "PostViewSet.list"),
                route("POST", "/api/posts", "PostViewSet.create"),
                route("GET", "/api/posts/{id}", "PostViewSet.retrieve"),
                route("DELETE", "/api/posts/{id}", "PostViewSet.destroy"),
                route("GET", "/health", "health"),
            ]},
            "auth": {"strategy": "JWT", "protected_routes": []},
            "project": {"stack": ["Django"]},
        }

    def test_one_question_per_resource(self):
        questions = gqb.gen_coding_questions(self._graph(), {})
        resources = [q["text"] for q in questions]
        self.assertEqual(len(questions), 3, "\n".join(resources))
        posts = [t for t in resources if "/api/posts" in t][0]
        self.assertIn("also served by", posts)
        self.assertIn("DELETE /api/posts/{id}", posts)

    def test_protected_write_route_is_the_representative(self):
        graph = self._graph()
        graph["backend"]["routes"][0]["middleware"] = ["IsAuthenticated"]
        questions = gqb.gen_coding_questions(graph, {})
        posts = [q["text"] for q in questions if "/api/posts" in q["text"]][0]
        self.assertIn("GET /api/posts", posts)


class TestFeatureResolution(unittest.TestCase):
    """A URL names a route, not a component that happens to call it."""

    def _graph(self):
        return {
            "frontend": {"api_calls": [{
                "name": "fetch:/api/todos",
                "details": {"method": "GET", "endpoint": "/api/todos", "client": "fetch"},
                "evidence": {"file": "app/page.tsx", "lines": [5, 5],
                             "excerpt": "fetch('/api/todos')", "status": "code-verified"},
            }]},
            "backend": {"routes": [{
                "method": "GET", "path": "/api/todos", "handler": "GET",
                "evidence": {"file": "app/api/todos/route.ts", "lines": [5, 5],
                             "excerpt": "export async function GET", "status": "code-verified"},
            }]},
        }

    def test_route_wins_over_a_frontend_call_with_the_same_name(self):
        entry = gc.find_feature_entry(self._graph(), "api/todos")
        self.assertEqual(entry["path"], "/api/todos")
        self.assertEqual(entry["evidence"]["file"], "app/api/todos/route.ts")

    def test_handler_name_still_resolves(self):
        entry = gc.find_feature_entry(self._graph(), "GET")
        self.assertEqual(entry["path"], "/api/todos")

    def test_unknown_feature_returns_none(self):
        self.assertIsNone(gc.find_feature_entry(self._graph(), "payments"))


class TestChallengeRelocation(TempRepo):
    def test_challenge_is_built_from_the_defining_file(self):
        _write(self.tmpdir, "shop/urls.py", '''
from django.urls import path
from shop import views

urlpatterns = [
    path("orders", views.list_orders, name="orders"),
]
''')
        _write(self.tmpdir, "shop/views.py", '''
def list_orders(request):
    orders = fetch_orders()
    return build_response(orders)
''')
        _write(self.tmpdir, "shop/models.py", "class Order:\n    pass\n")
        facts = detect.detect_all(self.tmpdir)
        import scan_repository as scanner
        graph = build_graph.build_graph(
            self.tmpdir, scanner.scan_repository(self.tmpdir), facts
        )
        (self.tmpdir / ".project-defense").mkdir(exist_ok=True)
        (self.tmpdir / ".project-defense" / "project-graph.json").write_text(
            json.dumps(graph), encoding="utf-8"
        )

        challenge_id = gc.generate_challenge(
            self.tmpdir, "list_orders", "function_reconstruction", "medium"
        )
        challenge_dir = self.tmpdir / ".project-defense" / "challenges" / challenge_id
        manifest = json.loads((challenge_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(
            any("views.py" in ref["file"] for ref in manifest["source_references"]),
            manifest["source_references"],
        )
        starter = (challenge_dir / "workspace" / manifest["workspace"]["starter_file"])
        if not starter.exists():
            starter = challenge_dir / "starter" / manifest["workspace"]["starter_file"]
        starter_text = starter.read_text(encoding="utf-8")
        self.assertNotIn("fetch_orders()", starter_text)
        self.assertIn("NotImplementedError", starter_text)
        self.assertEqual(facts["python"]["routes"][0]["handler"], "views.list_orders")


if __name__ == "__main__":
    unittest.main()
