#!/usr/bin/env python3
"""
test_generic_detection.py -- Tests for the multi-language packs and the Phase 4
correction pipeline.

Every test writes a miniature project of one ecosystem into a temp directory and
asserts what the pack extracts from it. The point is not that the regexes run; it
is that a project in that ecosystem gets a real interview instead of five generic
questions, and that a wrong guess stays visible (file, lines, excerpt) so the
human can correct it.

Covered here:
  - Go: gin group prefixes, net/http, chi, GORM structs, JWT/bcrypt signals
  - Ruby: Rails routes.rb (namespace, resources), Sinatra, ActiveRecord
  - PHP: Laravel routes, apiResource expansion, prefix groups, Eloquent
  - Java: Spring class + method mapping, @PreAuthorize
  - C#: controller routes with [controller] placeholder, minimal APIs
  - Rust: Axum and Actix
  - Kotlin: Ktor
  - Elixir: Phoenix routes
  - Prisma schema models
  - manifest parsers, framework names, correction application
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import apply_corrections as ac
import detect_stack_generic as gen
import scan_repository as sr


class _ProjectCase(unittest.TestCase):
    """Writes files into a temp repo and runs the generic packs over them."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pdc-generic-"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel: str, content: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def detect(self):
        files = sorted(p for p in self.root.rglob("*") if p.is_file())
        return gen.detect_generic(self.root, files)

    def routes(self):
        return [(r["method"], r["path"]) for r in self.detect()["routes"]]


class TestGo(_ProjectCase):
    def test_gin_group_prefix_is_applied(self):
        self.write("main.go", """package main

func main() {
\tr := gin.Default()
\tapi := r.Group("/api")
\tapi.GET("/notes", handlers.ListNotes)
\tapi.POST("/notes", handlers.CreateNote)
\tapi.DELETE("/notes/:id", handlers.DeleteNote)
}
""")
        self.assertEqual(self.routes(), [
            ("DELETE", "/api/notes/:id"),
            ("GET", "/api/notes"),
            ("POST", "/api/notes"),
        ])

    def test_net_http_and_chi_handlers(self):
        self.write("server.go", """package main

func routes() {
\thttp.HandleFunc("/healthz", health)
\tr.Method("GET", "/api/v1/items", listItems)
}
""")
        self.assertEqual(self.routes(), [("ANY", "/healthz"), ("GET", "/api/v1/items")])

    def test_gorm_struct_is_a_model_with_field_types(self):
        self.write("models/note.go", """package models

type Note struct {
\tID    uint   `json:"id"`
\tTitle string `json:"title"`
\tDone  bool   `json:"done"`
}
""")
        models = self.detect()["models"]
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["name"], "Note")
        fields = {f["name"]: f["type"] for f in models[0]["fields"]}
        self.assertEqual(fields, {"id": "uint", "title": "string", "done": "bool"})

    def test_helper_structs_are_not_models(self):
        self.write("models/handler.go", """package models

type RequestBody struct {
\tName string `json:"name"`
}
""")
        self.assertEqual(self.detect()["models"], [])

    def test_jwt_and_bcrypt_signals(self):
        self.write("auth/auth.go", """package auth

func hash(pw string) { bcrypt.GenerateFromPassword([]byte(pw), 10) }
func verify(tok string) { jwt.Parse(tok, keyFunc) }
""")
        kinds = self.detect()["auth"]
        self.assertIn("hash", kinds)
        self.assertIn("token", kinds)

    def test_test_files_are_skipped(self):
        self.write("main_test.go", """package main

func TestX(t *testing.T) {
\tr.GET("/not-a-real-route", handler)
}
""")
        self.assertEqual(self.routes(), [])


class TestRuby(_ProjectCase):
    def test_rails_namespace_and_resources(self):
        self.write("config/routes.rb", """Rails.application.routes.draw do
  namespace :api do
    resources :posts, only: [:index, :show]
    get "/health", to: "health#show"
  end
end
""")
        routes = self.routes()
        self.assertIn(("GET", "/api/posts"), routes)
        self.assertIn(("GET", "/api/posts/:id"), routes)
        self.assertIn(("GET", "/api/health"), routes)
        # only: [:index, :show] means no create/update/destroy
        self.assertNotIn(("POST", "/api/posts"), routes)

    def test_sinatra_route(self):
        self.write("app.rb", """require 'sinatra'

get "/ping" do
  "pong"
end
""")
        self.assertEqual(self.routes(), [("GET", "/ping")])

    def test_active_record_model(self):
        self.write("app/models/post.rb", """class Post < ApplicationRecord
  belongs_to :author
  has_many :comments
end
""")
        models = self.detect()["models"]
        self.assertEqual(models[0]["name"], "Post")
        kinds = {f["name"]: f["type"] for f in models[0]["fields"]}
        self.assertEqual(kinds.get("author"), "belongs_to")
        self.assertEqual(kinds.get("comments"), "has_many")


class TestPhp(_ProjectCase):
    def test_laravel_routes_and_api_resource(self):
        self.write("routes/api.php", """<?php
Route::get('/status', [StatusController::class, 'show']);
Route::apiResource('posts', PostController::class);
""")
        routes = self.routes()
        self.assertIn(("GET", "/status"), routes)
        self.assertIn(("GET", "/posts"), routes)
        self.assertIn(("POST", "/posts"), routes)
        self.assertIn(("DELETE", "/posts/{id}"), routes)

    def test_prefix_group_applies(self):
        self.write("routes/web.php", """<?php
Route::prefix('api')->group(function () {
    Route::get('/notes', [NoteController::class, 'index']);
});
Route::get('/outside', [NoteController::class, 'outside']);
""")
        routes = self.routes()
        self.assertIn(("GET", "/api/notes"), routes)
        self.assertIn(("GET", "/outside"), routes)

    def test_route_middleware_marks_protection(self):
        self.write("routes/api.php", """<?php
Route::post('/posts', [PostController::class, 'store'])->middleware('auth:sanctum');
""")
        route = self.detect()["routes"][0]
        self.assertEqual(route["middleware"], ["auth:sanctum"])

    def test_middleware_does_not_leak_to_the_previous_route(self):
        """A guarded line must not protect the route above it."""
        self.write("routes/api.php", """<?php
Route::get('/posts', [PostController::class, 'index']);
Route::post('/posts', [PostController::class, 'store'])->middleware('auth:sanctum');
""")
        detected = self.detect()["routes"]
        by_method = {r["method"]: r for r in detected}
        self.assertNotIn("middleware", by_method["GET"], "the line above carries no guard")
        self.assertEqual(by_method["POST"]["middleware"], ["auth:sanctum"])

    def test_sanctum_is_not_reported_as_jwt(self):
        """Sanctum issues opaque tokens; calling them JWT would be a wrong claim."""
        self.write("routes/api.php", """<?php
Route::post('/login', [AuthController::class, 'login'])->middleware('auth:sanctum');
""")
        auth = self.detect()["auth"]
        self.assertIn("api_key", auth)
        self.assertNotIn("token", auth)

    def test_eloquent_model_fillable(self):
        self.write("app/Models/Post.php", """<?php
class Post extends Model
{
    protected $fillable = ['title', 'body'];
}
""")
        models = self.detect()["models"]
        self.assertEqual(models[0]["name"], "Post")
        self.assertEqual([f["name"] for f in models[0]["fields"]], ["title", "body"])


class TestJava(_ProjectCase):
    def test_spring_class_and_method_mapping(self):
        self.write("src/NotesController.java", """@RestController
@RequestMapping("/api/notes")
public class NotesController {

    @GetMapping("")
    public List<Note> list() { return null; }

    @PostMapping("/{id}/publish")
    public Note publish(@PathVariable Long id) { return null; }

    @PreAuthorize("hasRole('ADMIN')")
    @DeleteMapping("/{id}")
    public void delete(@PathVariable Long id) { }
}
""")
        routes = self.detect()["routes"]
        pairs = [(r["method"], r["path"]) for r in routes]
        self.assertIn(("GET", "/api/notes"), pairs)
        self.assertIn(("POST", "/api/notes/{id}/publish"), pairs)
        delete = [r for r in routes if r["method"] == "DELETE"][0]
        self.assertEqual(delete["middleware"], ["@PreAuthorize"])

    def test_entity_becomes_a_model(self):
        self.write("src/Note.java", """@Entity
public class Note {
    private String title;
}
""")
        self.assertEqual([m["name"] for m in self.detect()["models"]], ["Note"])


class TestCSharp(_ProjectCase):
    def test_controller_with_placeholder(self):
        self.write("Controllers/NotesController.cs", """[Route("api/[controller]")]
public class NotesController : ControllerBase
{
    [HttpGet]
    public IActionResult List() { return Ok(); }

    [Authorize]
    [HttpPost]
    public IActionResult Create() { return Ok(); }
}
""")
        routes = self.detect()["routes"]
        pairs = [(r["method"], r["path"]) for r in routes]
        self.assertIn(("GET", "/api/notes"), pairs)
        create = [r for r in routes if r["method"] == "POST"][0]
        self.assertEqual(create["path"], "/api/notes")
        self.assertEqual(create["middleware"], ["[Authorize]"])

    def test_minimal_api(self):
        self.write("Program.cs", """app.MapGet("/api/notes", (HttpContext ctx) => "ok");
""")
        self.assertEqual(self.routes(), [("GET", "/api/notes")])


class TestRust(_ProjectCase):
    def test_axum_and_actix(self):
        self.write("src/main.rs", """fn app() -> Router {
    Router::new()
        .route("/api/notes", get(list_notes))
        .route("/api/notes", post(create_note))
}

#[get("/health")]
async fn health() -> &'static str { "ok" }
""")
        # Sorted by (method, path): the order is fixed so output is stable.
        self.assertEqual(self.routes(), [
            ("GET", "/api/notes"),
            ("GET", "/health"),
            ("POST", "/api/notes"),
        ])

    def test_jsonwebtoken_signal(self):
        self.write("src/auth.rs", """use jsonwebtoken::{encode, decode};
""")
        self.assertIn("token", self.detect()["auth"])


class TestKotlin(_ProjectCase):
    def test_ktor_routes(self):
        self.write("src/Application.kt", """fun Application.module() {
    routing {
        get("/api/notes") { call.respond(notes) }
        post("/api/notes") { call.respond(201) }
    }
}
""")
        self.assertEqual(self.routes(), [("GET", "/api/notes"), ("POST", "/api/notes")])


class TestElixirAndPrisma(_ProjectCase):
    def test_phoenix_routes(self):
        self.write("lib/router.ex", """defmodule NotesWeb.Router do
  scope "/api", NotesWeb do
    get "/notes", NoteController, :index
    resources "/notes", NoteController, except: [:edit]
  end
end
""")
        routes = self.routes()
        self.assertIn(("GET", "/notes"), routes)

    def test_prisma_models(self):
        self.write("prisma/schema.prisma", """model Note {
  id    Int    @id @default(autoincrement())
  title String
  body  String?
}
""")
        models = self.detect()["models"]
        self.assertEqual(models[0]["name"], "Note")
        fields = {f["name"]: f["type"] for f in models[0]["fields"]}
        self.assertEqual(fields["title"], "String")
        self.assertEqual(fields["body"], "String")


class TestEvidenceAndDeduplication(_ProjectCase):
    def test_every_route_cites_a_file_and_line(self):
        self.write("main.go", """package main

func main() {
\tapi := r.Group("/api")
\tapi.GET("/notes", handlers.ListNotes)
}
""")
        route = self.detect()["routes"][0]
        self.assertEqual(route["evidence"]["file"], "main.go")
        self.assertEqual(route["evidence"]["lines"], [5, 5])
        self.assertIn("/notes", route["evidence"]["excerpt"])
        self.assertEqual(route["evidence"]["status"], "code-verified")

    def test_duplicate_paths_collapse(self):
        self.write("a.go", """package main

func a() { api := r.Group("/api"); api.GET("/x", h) }
""")
        self.write("b.go", """package main

func b() { api := r.Group("/api"); api.GET("/x", h) }
""")
        self.assertEqual(self.routes(), [("GET", "/api/x")])


class TestRailsControllerGuards(_ProjectCase):
    """Rails protects a controller, so the guard has to reach the routes."""

    def test_before_action_protects_only_the_unguarded_actions(self):
        self.write("config/routes.rb", """Rails.application.routes.draw do
  resources :posts, only: [:index, :show, :create, :destroy]
end
""")
        self.write("app/controllers/posts_controller.rb", """class PostsController < ApplicationController
  before_action :authenticate_user!, except: [:index, :show]

  def create; end
end
""")
        graph = self._graph_from_detect()
        protected = {p["name"] for p in graph}
        self.assertIn("POST /posts", protected)
        self.assertIn("DELETE /posts/:id", protected)
        self.assertNotIn("GET /posts", protected, "an excepted action stays public")

    def _graph_from_detect(self):
        files = sorted(p for p in self.root.rglob("*") if p.is_file())
        detected = gen.detect_generic(self.root, files)
        routes = []
        guards = {g["controller"]: g for g in detected["guards"]}
        for route in detected["routes"]:
            handler = route["handler"]
            controller = handler.split("#", 1)[0] if "#" in handler else ""
            guard = guards.get(controller)
            if guard and handler.split("#", 1)[1] not in guard["except"]:
                routes.append({"name": "{} {}".format(route["method"], route["path"])})
        return routes


class TestManifestParsers(unittest.TestCase):
    def test_go_mod(self):
        deps = sr.parse_go_mod("""module example.com/x

go 1.22

require github.com/gin-gonic/gin v1.10.0
require (
\tgorm.io/gorm v1.25.7
)
""")
        self.assertIn("github.com/gin-gonic/gin", deps)
        self.assertIn("gorm.io/gorm", deps)

    def test_cargo_toml_only_dependency_tables(self):
        deps = sr.parse_cargo_toml("""[package]
name = "x"

[dependencies]
axum = "0.7"

[dev-dependencies]
tower = "0.4"
""")
        self.assertEqual(sorted(deps), ["axum", "tower"])

    def test_gemfile_composer_gradle_mix(self):
        self.assertEqual(sr.parse_gemfile('gem "rails"\ngem \'pg\'\n'), ["rails", "pg"])
        self.assertEqual(
            sr.parse_composer_json('{"require": {"laravel/framework": "^10"}}'),
            ["laravel/framework"],
        )
        self.assertEqual(
            sr.parse_gradle("implementation 'org.springframework.boot:spring-boot-starter-web:3.1'"),
            ["org.springframework.boot:spring-boot-starter-web:3.1"],
        )
        self.assertEqual(sr.parse_mix_exs('defp deps do\n [{:phoenix, "~> 1.7"}]\nend'), ["phoenix"])


class TestFrameworkNamesForOtherStacks(unittest.TestCase):
    def _detect(self, deps):
        return sr.detect_framework(deps, Path("."))

    def test_go_frameworks(self):
        result = self._detect(["github.com/gin-gonic/gin", "gorm.io/gorm", "github.com/golang-jwt/jwt/v5"])
        self.assertIn("Go (Gin)", result["backend"])
        self.assertIn("GORM", result["database"])
        self.assertIn("JWT", result["other"])

    def test_ruby_php_java_rust_csharp_elixir(self):
        self.assertIn("Ruby on Rails", self._detect(["rails", "pg"])["backend"])
        self.assertIn("Laravel", self._detect(["laravel/framework"])["backend"])
        self.assertIn(
            "Spring Boot",
            self._detect(["org.springframework.boot:spring-boot-starter-web"])["backend"],
        )
        self.assertIn("Rust (axum)", self._detect(["axum", "sqlx"])["backend"])
        self.assertIn(
            "ASP.NET Core",
            self._detect(["Microsoft.AspNetCore.App"])["backend"],
        )
        self.assertIn("Phoenix", self._detect(["phoenix", "ecto_sql"])["backend"])

    def test_no_false_positive_from_a_short_substring(self):
        # "imagine" contains "gin"; a bare substring rule would call it Gin.
        self.assertEqual(self._detect(["imagine-imaging-lib"])["backend"], [])


class TestCorrectionsPipeline(_ProjectCase):
    def _graph(self):
        return {
            "project": {"stack": ["Go (Gin)"]},
            "backend": {"routes": [
                {"method": "GET", "path": "/api/notes", "handler": "h",
                 "evidence": {"file": "main.go", "lines": [1, 1], "excerpt": "api.GET", "status": "code-verified"}},
            ]},
            "data": {"models": [
                {"name": "Note", "fields": [], "evidence": {"file": "n.go", "lines": [1, 1], "excerpt": "type Note", "status": "code-verified"}},
            ]},
            "frontend": {"components": []},
            "auth": {"strategy": "other"},
            "uncertainties": [{"question": "Which DB?", "context": "", "evidence": {"file": "x", "lines": [1, 1], "excerpt": "y", "status": "UNVERIFIED"}}],
        }

    def test_confirmed_route_becomes_user_provided(self):
        graph = self._graph()
        report = ac.apply_corrections(graph, {
            "route:GET /api/notes": {"decision": "confirmed", "note": "checked in main.go"},
        })
        self.assertEqual(report["applied"], ["route:GET /api/notes"])
        route = graph["backend"]["routes"][0]
        self.assertEqual(route["evidence"]["status"], "user-provided")
        self.assertIn("checked in main.go", route["evidence"]["excerpt"])

    def test_unknown_marks_unverified(self):
        graph = self._graph()
        ac.apply_corrections(graph, {"model:Note": {"decision": "unknown"}})
        self.assertEqual(graph["data"]["models"][0]["evidence"]["status"], "UNVERIFIED")

    def test_auth_and_stack_corrections_need_a_value(self):
        graph = self._graph()
        report = ac.apply_corrections(graph, {
            "auth:strategy": {"decision": "corrected", "value": "JWT"},
            "project:stack": {"decision": "corrected", "value": ["Go (Gin)", "PostgreSQL"]},
        })
        self.assertEqual(sorted(report["applied"]), ["auth:strategy", "project:stack"])
        self.assertEqual(graph["auth"]["strategy"], "JWT")
        self.assertEqual(graph["project"]["stack"], ["Go (Gin)", "PostgreSQL"])

    def test_unmatched_ids_are_reported_not_dropped(self):
        graph = self._graph()
        report = ac.apply_corrections(graph, {
            "route:DELETE /api/notes/{id}": {"decision": "confirmed"},
        })
        self.assertEqual(report["unmatched"], ["route:DELETE /api/notes/{id}"])

    def test_bad_id_is_refused_with_the_grammar(self):
        with self.assertRaises(SystemExit) as ctx:
            ac.validate_id("notes")
        self.assertIn("route:<METHOD>", str(ctx.exception.code))

    def test_corrections_survive_a_rebuild(self):
        """The whole point: build_graph must read corrections.json."""
        self.write("go.mod", "module x\n\nrequire github.com/gin-gonic/gin v1.10.0\n")
        self.write("main.go", """package main

func main() {
\tapi := r.Group("/api")
\tapi.GET("/notes", handlers.ListNotes)
}
""")
        defense = self.root / ".project-defense"
        defense.mkdir(exist_ok=True)
        (defense / "corrections.json").write_text(json.dumps({
            "auth:strategy": {"decision": "corrected", "value": "JWT",
                              "note": "custom middleware"},
        }), encoding="utf-8")

        env = dict(SCAN_ENV)
        for script in ("scan_repository.py", "detect_code_facts.py", "build_graph.py"):
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / script), str(self.root)],
                capture_output=True, text=True, env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

        graph = json.loads((defense / "project-graph.json").read_text())
        self.assertEqual(graph["auth"]["strategy"], "JWT",
                         "A corrected auth strategy must survive the rebuild")
        self.assertTrue(graph["backend"]["routes"])


import os  # noqa: E402

SCAN_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


if __name__ == "__main__":
    unittest.main(verbosity=2)
