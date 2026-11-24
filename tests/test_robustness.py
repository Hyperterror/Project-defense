#!/usr/bin/env python3
"""
test_robustness.py -- Regression tests for the fixes that came out of
reviewing the analysis pipeline.

Covered:
  - the scanner never reads dependency/build directories (node_modules etc.)
  - .project-defenseignore is honoured by both the scanner and the detector
  - JS/TS practice challenges no longer ship the original implementation
  - every generated question carries a rubric (category fallback)
  - a question-specific rubric only applies when the question is on-topic
  - unscored answers are not counted as zero in the final score
  - graph freshness is detected against git HEAD
  - no Python 3.10-only annotations leak into the stdlib-only scripts
  - challenge syntax checks match the starter file type

Run: python3 -m unittest discover -s tests -p "test_*.py"
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

import assess as assess_mod  # noqa: E402
import check_graph_freshness as cgf  # noqa: E402
import generate_challenge as gc  # noqa: E402
import generate_question_bank as gqb  # noqa: E402
import path_filters  # noqa: E402
import detect_code_facts as detect  # noqa: E402
import scan_repository as scanner  # noqa: E402
import score_report as sr  # noqa: E402


JS_GRAPH = {
    "session_identity": "test-identity",
    "project": {
        "name": "js-app",
        "purpose": "A JS app.",
        "stack": ["React"],
        "entry_points": [{"file": "src/Widget.jsx", "type": "frontend"}],
    },
    "frontend": {
        "pages": [],
        "components": [
            {
                "name": "Widget",
                "details": {"type": "component"},
                "evidence": {
                    "file": "src/Widget.jsx",
                    "lines": [1, 10],
                    "excerpt": "export default function Widget()",
                    "status": "code-verified",
                },
            }
        ],
        "state_management": [],
        "api_calls": [],
    },
    "backend": {"routes": [], "middleware": [], "controllers": [], "services": []},
    "data": {"models": [], "relationships": [], "migrations": []},
    "auth": {"strategy": "JWT", "token_handling": "Bearer", "protected_routes": []},
    "user_flows": [],
    "data_flows": [],
    "risks": [],
    "uncertainties": [],
}

SAMPLE_JSX = '''import React from "react";

export default function Widget({ id }) {
  const label = `Widget ${id}`;
  if (id < 0) {
    return null;
  }
  return <span>{label}</span>;
}
'''


def _write_js_fixture(root: Path) -> None:
    defense = root / ".project-defense"
    defense.mkdir(parents=True, exist_ok=True)
    (defense / "project-graph.json").write_text(json.dumps(JS_GRAPH), encoding="utf-8")
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "Widget.jsx").write_text(SAMPLE_JSX, encoding="utf-8")


class TestScannerFilters(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-robust-scan-"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scanner_ignores_dependency_dirs(self):
        """A dependency's package.json must not shape the project's stack."""
        (self.tmpdir / "package.json").write_text(
            json.dumps({"name": "app", "dependencies": {"express": "^4"}}),
            encoding="utf-8",
        )
        dep = self.tmpdir / "node_modules" / "fakepkg"
        dep.mkdir(parents=True)
        (dep / "package.json").write_text(
            json.dumps({"name": "fakepkg", "dependencies": {"react": "^18", "mongoose": "^7"}}),
            encoding="utf-8",
        )
        (dep / "index.js").write_text("console.log(process.env.LEAKED_VAR)", encoding="utf-8")

        facts = scanner.scan_repository(self.tmpdir)

        self.assertEqual(list(facts["dependency_manifests"]), ["package.json"])
        self.assertEqual(facts["frameworks"]["frontend"], [],
                         "React must not be detected from a dependency")
        self.assertEqual(facts["frameworks"]["database"], [],
                         "MongoDB must not be detected from a dependency")
        self.assertEqual(facts["env_vars"], [],
                         "env vars must not be harvested from dependencies")
        self.assertEqual(facts["entry_points"], [],
                         "node_modules entry points must not be listed")

    def test_ignore_file_excludes_paths(self):
        (self.tmpdir / ".project-defenseignore").write_text(
            "# generated code\nvendor/\n*.generated.js\n", encoding="utf-8"
        )
        (self.tmpdir / "src").mkdir()
        (self.tmpdir / "src" / "keep.js").write_text("", encoding="utf-8")
        (self.tmpdir / "src" / "skip.generated.js").write_text("", encoding="utf-8")
        vendor = self.tmpdir / "vendor" / "lib"
        vendor.mkdir(parents=True)
        (vendor / "thing.js").write_text("", encoding="utf-8")

        patterns = path_filters.load_ignore_patterns(self.tmpdir)
        seen = {
            p.relative_to(self.tmpdir).as_posix()
            for p in path_filters.walk_files(self.tmpdir, patterns)
        }
        self.assertIn("src/keep.js", seen)
        self.assertNotIn("src/skip.generated.js", seen)
        self.assertNotIn("vendor/lib/thing.js", seen)

    def test_negation_rule_is_supported(self):
        (self.tmpdir / ".project-defenseignore").write_text(
            "*.js\n!keep.js\n", encoding="utf-8"
        )
        (self.tmpdir / "keep.js").write_text("", encoding="utf-8")
        (self.tmpdir / "drop.js").write_text("", encoding="utf-8")
        patterns = path_filters.load_ignore_patterns(self.tmpdir)
        seen = {p.name for p in path_filters.walk_files(self.tmpdir, patterns)}
        self.assertIn("keep.js", seen)
        self.assertNotIn("drop.js", seen)


class TestJavascriptChallenges(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-robust-js-"))
        _write_js_fixture(self.tmpdir)
        self.original = (self.tmpdir / "src" / "Widget.jsx").read_text(encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _starter(self, challenge_id):
        starter_dir = self.tmpdir / ".project-defense" / "challenges" / challenge_id / "starter"
        files = list(starter_dir.iterdir())
        self.assertEqual(len(files), 1)
        return files[0]

    def test_function_reconstruction_removes_body(self):
        """The starter must not contain the original implementation."""
        cid = gc.generate_challenge(self.tmpdir, "Widget", "function_reconstruction", "medium")
        text = self._starter(cid).read_text(encoding="utf-8")

        self.assertIn("TODO", text)
        self.assertIn("Not implemented", text)
        self.assertNotIn('const label = `Widget ${id}`', text,
                         "the original implementation must be removed")
        self.assertIn("export default function Widget({ id })", text,
                      "the signature must be preserved")

    def test_body_stubbing_handles_braces_in_strings(self):
        """Braces inside strings and templates must not truncate the stub."""
        source = '''export default function Widget() {
  const s = "a } brace";
  const t = `x ${1 + 1}`;
  return s + t;
}
'''
        (self.tmpdir / "src" / "Widget.jsx").write_text(source, encoding="utf-8")
        cid = gc.generate_challenge(self.tmpdir, "Widget", "function_reconstruction", "medium")
        text = self._starter(cid).read_text(encoding="utf-8")
        self.assertNotIn("return s + t;", text)
        self.assertTrue(text.rstrip().endswith("}"), "closing brace must survive")

    def test_nested_functions_do_not_truncate_file(self):
        """Replacing an inner body must not shift the outer span's offsets."""
        source = """export function useAuth() {
  const login = async (email, password) => {
    return axios.post("/login", { email, password });
  };
  return { login };
}
"""
        (self.tmpdir / "src" / "Widget.jsx").write_text(source, encoding="utf-8")
        cid = gc.generate_challenge(self.tmpdir, "Widget", "function_reconstruction", "medium")
        text = self._starter(cid).read_text(encoding="utf-8")

        self.assertNotIn("axios.post", text)
        self.assertTrue(text.rstrip().endswith("}"), "the closing brace must survive")
        self.assertLess(len(text), len(source) + 200)

    def test_callback_bodies_are_stubbed(self):
        """Route/middleware callbacks must be stubbed too, not just declarations.

        A file built from `app.get(..., (req, res) => {...})` has no function
        declarations at all, which is how a starter used to ship verbatim.
        """
        source = """const express = require("express");

const app = express();

app.get("/api/health", (req, res) => {
  res.json({ status: "ok" });
});

app.use((err, req, res, next) => {
  res.status(500).json({ error: err.message });
});

module.exports = app;
"""
        (self.tmpdir / "src" / "Widget.jsx").write_text(source, encoding="utf-8")
        cid = gc.generate_challenge(self.tmpdir, "Widget", "function_reconstruction", "medium")
        text = self._starter(cid).read_text(encoding="utf-8")

        self.assertIn("TODO", text)
        self.assertNotIn('res.json({ status: "ok" })', text,
                         "the callback body must be removed")
        self.assertIn('app.get("/api/health"', text,
                      "the call scaffolding must be preserved")
        self.assertIn("module.exports = app;", text)

    def test_identical_starter_is_rejected(self):
        """A challenge whose starter equals its source must fail, not ship."""
        (self.tmpdir / "src" / "Widget.jsx").write_text(
            'export const VERSION = "1.0.0";', encoding="utf-8"
        )
        with self.assertRaises(SystemExit) as ctx:
            gc.generate_challenge(self.tmpdir, "Widget", "function_reconstruction", "medium")
        self.assertIn("identical to the original", str(ctx.exception))

    def test_test_writing_generates_jest_skeleton(self):
        cid = gc.generate_challenge(self.tmpdir, "Widget", "test_writing", "easy")
        starter = self._starter(cid)
        self.assertEqual(starter.name, "Widget.test.jsx")
        text = starter.read_text(encoding="utf-8")
        self.assertIn("describe(", text)
        self.assertIn("test(", text)
        self.assertNotIn("import unittest", text)

    def test_checks_match_file_type(self):
        cid = gc.generate_challenge(self.tmpdir, "Widget", "function_reconstruction", "easy")
        manifest = json.loads(
            (self.tmpdir / ".project-defense" / "challenges" / cid / "manifest.json")
            .read_text(encoding="utf-8")
        )
        ids = [c["id"] for c in manifest["checks"]]
        # .jsx cannot be syntax-checked without a toolchain, so the structural
        # check is used rather than the Python AST check.
        self.assertIn("check-file-present", ids)

    def test_unknown_feature_fails_loudly(self):
        """A feature absent from the graph must not produce a fabricated challenge."""
        with self.assertRaises(SystemExit) as ctx:
            gc.generate_challenge(self.tmpdir, "does-not-exist", "function_reconstruction", "easy")
        message = str(ctx.exception)
        self.assertIn("was not found in the project graph", message)
        self.assertIn("Widget", message, "the error should list available features")

    def test_original_file_untouched(self):
        gc.generate_challenge(self.tmpdir, "Widget", "function_reconstruction", "hard")
        self.assertEqual(
            (self.tmpdir / "src" / "Widget.jsx").read_text(encoding="utf-8"),
            self.original,
        )


class TestRubricCoverage(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-robust-rubric-"))
        defense = self.tmpdir / ".project-defense"
        defense.mkdir()
        (defense / "project-graph.json").write_text(json.dumps(JS_GRAPH), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_every_question_has_a_rubric(self):
        bank = gqb.generate_question_bank(self.tmpdir)
        self.assertGreater(len(bank["questions"]), 0)
        for q in bank["questions"]:
            self.assertTrue(q.get("rubric_id"),
                            "{} has no rubric".format(q["id"]))

    def test_question_specific_rubric_requires_matching_topic(self):
        rubrics = gqb._load_rubrics()
        off_topic = gqb._rubric_for(rubrics, "q-e001", "explanation",
                                    "Walk me through the Widget component.")
        on_topic = gqb._rubric_for(rubrics, "q-e001", "explanation",
                                   "Walk me through the login flow and JWT verification.")
        self.assertEqual(off_topic, "explanation-generic-v1")
        self.assertEqual(on_topic, "explanation-auth-v1")


class TestScoringIntegrity(unittest.TestCase):
    def test_unscored_answers_are_not_counted_as_zero(self):
        session = {
            "session_id": "sess-test",
            "questions": [
                {"question_id": "q-e001", "category": "explanation",
                 "answer": "good answer", "scores": {"a": 3}, "rubric_id": "r"},
                {"question_id": "q-e002", "category": "explanation",
                 "answer": "answer with no rubric", "scores": {}, "rubric_id": ""},
            ],
        }
        result = sr.compute_scores(session)
        self.assertAlmostEqual(result["categories"]["Architecture"]["score"], 1.0, places=4)
        self.assertEqual(result["categories"]["Architecture"]["scored_count"], 1)
        self.assertEqual(result["categories"]["Architecture"]["unscored"], ["q-e002"])

    def test_heuristic_scores_are_flagged(self):
        session = {
            "session_id": "sess-test",
            "questions": [
                {"question_id": "q-e001", "category": "explanation",
                 "answer": "x", "scores": {"a": 2}, "rubric_id": "r",
                 "scored_by": "heuristic"},
            ],
        }
        result = sr.compute_scores(session)
        self.assertEqual(result["categories"]["Architecture"]["heuristic_scored"], 1)


class TestGraphFreshness(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-robust-fresh-"))
        self.defense = self.tmpdir / ".project-defense"
        self.defense.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.tmpdir)] + list(args),
            capture_output=True, text=True,
        )

    def _have_git(self):
        try:
            return self._git("--version").returncode == 0
        except Exception:
            return False

    def test_missing_graph_reports_not_fresh(self):
        report = cgf.check_freshness(self.tmpdir)
        self.assertFalse(report["fresh"])
        self.assertIn("not found", report["reason"])

    def test_stale_graph_is_detected(self):
        if not self._have_git():
            self.skipTest("git not available")
        self._git("init", "-q")
        (self.tmpdir / "a.txt").write_text("one\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "one")
        head = self._git("rev-parse", "HEAD").stdout.strip()

        (self.defense / "project-graph.json").write_text(
            json.dumps({"git_head": head, "analyzed_at": "2024-01-01T00:00:00+00:00"}),
            encoding="utf-8",
        )
        self.assertTrue(cgf.check_freshness(self.tmpdir)["fresh"])

        (self.tmpdir / "a.txt").write_text("two\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "two")

        report = cgf.check_freshness(self.tmpdir)
        self.assertFalse(report["fresh"])
        self.assertEqual(report["commits_behind"], 1)


    def test_fingerprint_catches_edits_without_git(self):
        """A repo with no git history still gets a stale verdict after an edit."""
        src = self.tmpdir / "src"
        src.mkdir()
        (src / "a.js").write_text("export function a() { return 1; }\n", encoding="utf-8")
        fingerprint = cgf.content_fingerprint(self.tmpdir)
        self.assertTrue(fingerprint)

        (self.defense / "project-graph.json").write_text(
            json.dumps({"git_head": "", "content_fingerprint": fingerprint}),
            encoding="utf-8",
        )
        report = cgf.check_freshness(self.tmpdir)
        self.assertEqual(report["checked_by"], "content_fingerprint")
        self.assertTrue(report["fresh"])

        (src / "a.js").write_text("export function a() { return 2; }\n", encoding="utf-8")
        report = cgf.check_freshness(self.tmpdir)
        self.assertFalse(report["fresh"])
        self.assertIn("changed since analysis", report["reason"])


class TestGraphEdges(unittest.TestCase):
    """File-level edges: the map behind 'what breaks if I delete this?'."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-robust-edges-"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_internal_imports_are_extracted_and_bare_specifiers_ignored(self):
        src = self.tmpdir / "src"
        src.mkdir()
        (src / "a.js").write_text(
            'const b = require("./b");' + chr(10) + 'const react = require("react");' + chr(10),
            encoding="utf-8",
        )
        (src / "b.js").write_text("export const x = 1;" + chr(10), encoding="utf-8")

        edges = detect.detect_imports(self.tmpdir, [src / "a.js", src / "b.js"])
        pairs = {(e["from"].replace("\\", "/"), e["to"].replace("\\", "/")) for e in edges}
        self.assertIn(("src/a.js", "src/b.js"), pairs)
        self.assertEqual(len(pairs), 1, "a bare package specifier must not become an edge")

    def test_python_relative_imports_resolve(self):
        pkg = self.tmpdir / "app"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "routes.py").write_text("from .models import Thing" + chr(10), encoding="utf-8")
        (pkg / "models.py").write_text("class Thing: pass" + chr(10), encoding="utf-8")

        edges = detect.detect_imports(
            self.tmpdir, [pkg / "routes.py", pkg / "models.py"]
        )
        targets = {e["to"].replace("\\", "/") for e in edges}
        self.assertIn("app/models.py", targets)

    def test_reverse_importers_drive_the_deletion_question(self):
        graph = {
            "relationships": [
                {"type": "imports", "from": "src/a.js", "to": "src/b.js"},
                {"type": "imports", "from": "src/c.js", "to": "src/b.js"},
                {"type": "tested_by", "from": "src/b.js", "to": "src/b.test.js"},
            ]
        }
        self.assertEqual(
            sorted(gqb._importers(graph, "src/b.js")), ["src/a.js", "src/c.js"]
        )

    def test_test_file_matching(self):
        src = self.tmpdir / "src"
        src.mkdir()
        (src / "auth.js").write_text("export function login() {}\n", encoding="utf-8")
        (src / "auth.test.js").write_text("test('x', () => {});\n", encoding="utf-8")
        edges = detect.detect_test_edges(
            self.tmpdir, [src / "auth.js", src / "auth.test.js"]
        )
        self.assertEqual(len(edges), 1)
        self.assertIn("auth.test.js", edges[0]["test"])


class TestChallengeScaffolding(unittest.TestCase):
    """Explainer + reference solution: teaching material that cannot leak."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-robust-scaffold-"))
        _write_js_fixture(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_explainer_and_solution_are_written(self):
        cid = gc.generate_challenge(self.tmpdir, "Widget", "function_reconstruction", "medium")
        challenge_dir = self.tmpdir / ".project-defense" / "challenges" / cid

        explainer = (challenge_dir / "explainer.md").read_text(encoding="utf-8")
        self.assertIn("## Definition of done", explainer)
        self.assertIn("## How you will be judged", explainer)
        self.assertNotIn("const label = `Widget ${id}`", explainer,
                         "the explainer must not contain the implementation")

        manifest = json.loads((challenge_dir / "manifest.json").read_text())
        self.assertEqual(manifest["explainer"], "explainer.md")
        solution = challenge_dir / manifest["solution_file"]
        self.assertTrue(solution.exists())
        self.assertIn("const label", solution.read_text(encoding="utf-8"))

    def test_workspace_never_contains_the_solution(self):
        cid = gc.generate_challenge(self.tmpdir, "Widget", "function_reconstruction", "medium")
        challenge_dir = self.tmpdir / ".project-defense" / "challenges" / cid
        subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "prepare_workspace.py"),
             str(self.tmpdir), "--challenge", cid],
            capture_output=True, text=True,
        )
        workspace_files = [p.name for p in (challenge_dir / "workspace").iterdir()]
        self.assertNotIn("solution", workspace_files)
        for name in workspace_files:
            text = (challenge_dir / "workspace" / name).read_text(encoding="utf-8")
            self.assertNotIn("const label", text,
                             "the workspace must never contain the implementation")


class TestPython38Compatibility(unittest.TestCase):
    def test_no_pep604_union_annotations(self):
        """Scripts advertise Python 3.8+; `X | None` annotations break 3.8/3.9."""
        offenders = []
        for path in sorted(SCRIPTS_DIR.glob("*.py")):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "->" in line and "|" in line.split("->", 1)[1]:
                    offenders.append("{}:{}".format(path.name, lineno))
        self.assertEqual(offenders, [], "PEP 604 unions found: {}".format(offenders))


class TestScoreReliability(unittest.TestCase):
    def test_labels(self):
        def cats(scored, heuristic):
            return {"categories": {"Architecture": {
                "scored_count": scored, "heuristic_scored": heuristic}}}

        self.assertEqual(assess_mod._score_reliability(cats(3, 3)), "heuristic-only")
        self.assertEqual(assess_mod._score_reliability(cats(3, 1)), "mixed")
        self.assertEqual(assess_mod._score_reliability(cats(3, 0)), "agent-scored")
        self.assertEqual(assess_mod._score_reliability(cats(0, 0)), "agent-scored")


if __name__ == "__main__":
    unittest.main(verbosity=2)
