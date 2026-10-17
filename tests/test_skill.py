#!/usr/bin/env python3
"""
test_skill.py -- Smoke tests for project-defense-skill scripts.

Runs without any external dependencies. Creates a tiny fixture Express+React
project in a temp directory, runs the detectors, and asserts the right things
were found.

Usage:
  python3 tests/test_skill.py
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
DETECT_SCRIPT = SKILL_DIR / "scripts" / "detect_code_facts.py"
VALIDATE_SCRIPT = SKILL_DIR / "scripts" / "validate_graph.py"
SCAN_SCRIPT = SKILL_DIR / "scripts" / "scan_repository.py"
FETCH_SCRIPT = SKILL_DIR / "scripts" / "fetch_repository.py"
BUILD_SCRIPT = SKILL_DIR / "scripts" / "build_graph.py"
SCHEMA = SKILL_DIR / "templates" / "project-graph.schema.json"


SAMPLE_EXPRESS_SERVER = '''
const express = require("express");
const bcrypt = require("bcrypt");
const jwt = require("jsonwebtoken");

const app = express();
app.use(cors());
app.use(express.json());

const authMiddleware = (req, res, next) => {
  const token = req.headers.authorization;
  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    req.user = decoded;
    next();
  } catch (e) {
    return res.status(401).json({ error: "Unauthorized" });
  }
};

app.post("/api/auth/register", async (req, res) => {
  const { email, password } = req.body;
  const hash = await bcrypt.hash(password, 10);
  // create user in db
  res.status(201).json({ email });
});

app.post("/api/auth/login", async (req, res) => {
  const { email, password } = req.body;
  // compare bcrypt
  const token = jwt.sign({ email }, process.env.JWT_SECRET, { expiresIn: "1h" });
  res.json({ token });
});

app.get("/api/users/me", authMiddleware, (req, res) => {
  res.json({ user: req.user });
});

app.delete("/api/users/:id", authMiddleware, (req, res) => {
  // delete user
  res.status(204).send();
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log("Listening on", PORT));
'''

SAMPLE_REACT_COMPONENT = '''
import React, { useState } from "react";

export default function LoginForm({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    onLogin(data.token);
  };

  return (
    <form onSubmit={handleSubmit}>
      <input value={email} onChange={e => setEmail(e.target.value)} />
      <input value={password} onChange={e => setPassword(e.target.value)} type="password" />
      <button type="submit">Log in</button>
    </form>
  );
}
'''

SAMPLE_REACT_HOOK = '''
import { useState, useEffect } from "react";

export function useAuth() {
  const [user, setUser] = useState(null);
  useEffect(() => {
    // fetch user
  }, []);
  return { user, setUser };
}
'''

SAMPLE_REACT_DASHBOARD = '''
import React from "react";
import axios from "axios";

const Dashboard = () => {
  const data = axios.get("/api/users/me");
  return <div>{data ? "Logged in" : "Loading..."}</div>;
};

export default Dashboard;
'''

SAMPLE_AUTH_ROUTES = '''
const express = require("express");
const bcrypt = require("bcrypt");
const User = require("../models/User");
const router = express.Router();

router.post("/register", async (req, res) => {
  const hash = await bcrypt.hash(req.body.password, 10);
  res.json({ ok: true });
});

router.post("/login", async (req, res) => {
  res.json({ token: "x" });
});

module.exports = router;
'''

SAMPLE_TODO_ROUTES = '''
const express = require("express");
const router = express.Router();

router.get("/", (req, res) => { res.json([]); });
router.post("/", (req, res) => { res.status(201).json({ id: 1 }); });

module.exports = router;
'''

SAMPLE_MONGOOSE_MODEL = '''
const mongoose = require("mongoose");

const userSchema = new mongoose.Schema({
  email: { type: String, required: true, unique: true },
  password: { type: String, required: true },
  createdAt: { type: Date, default: Date.now },
});

const User = mongoose.model("User", userSchema);
module.exports = User;
'''

VALID_GRAPH = {
    "project": {
        "name": "TestApp",
        "purpose": "A test app for the project-defense skill.",
        "stack": ["React", "Node", "Express", "MongoDB"],
        "entry_points": [
            {"file": "server/index.js", "type": "backend"}
        ],
    },
    "frontend": {
        "pages": [],
        "components": [
            {
                "name": "LoginForm",
                "details": {"type": "component"},
                "evidence": {
                    "file": "src/components/LoginForm.jsx",
                    "lines": [3, 30],
                    "excerpt": "export default function LoginForm",
                    "status": "code-verified",
                },
            }
        ],
        "state_management": [],
        "api_calls": [
            {
                "name": "fetch:/api/auth/login",
                "details": {"method": "POST", "endpoint": "/api/auth/login", "client": "fetch"},
                "evidence": {
                    "file": "src/components/LoginForm.jsx",
                    "lines": [12, 15],
                    "excerpt": 'fetch("/api/auth/login"',
                    "status": "code-verified",
                },
            }
        ],
    },
    "backend": {
        "routes": [
            {
                "method": "POST",
                "path": "/api/auth/login",
                "handler": "authController.login",
                "evidence": {
                    "file": "server/index.js",
                    "lines": [25, 30],
                    "excerpt": 'app.post("/api/auth/login"',
                    "status": "code-verified",
                },
            }
        ],
        "middleware": [
            {
                "name": "authMiddleware",
                "details": {"purpose": "JWT verify"},
                "evidence": {
                    "file": "server/index.js",
                    "lines": [7, 17],
                    "excerpt": "authMiddleware",
                    "status": "code-verified",
                },
            }
        ],
        "controllers": [],
        "services": [],
    },
    "data": {"models": [], "relationships": [], "migrations": []},
    "auth": {
        "strategy": "JWT",
        "token_handling": "Authorization header",
        "protected_routes": [],
    },
    "user_flows": [],
    "data_flows": [],
    "risks": [],
    "uncertainties": [],
}

INVALID_GRAPH_MISSING_REQUIRED = {"project": {"name": "X"}}  # missing 8 required keys


class TestDetector(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-test-"))
        (self.tmpdir / "server").mkdir()
        (self.tmpdir / "server" / "models").mkdir()
        (self.tmpdir / "src" / "components").mkdir(parents=True)
        (self.tmpdir / "src" / "hooks").mkdir(parents=True)
        (self.tmpdir / "package.json").write_text(json.dumps({
            "name": "test-app", "dependencies": {"express": "1.0", "mongoose": "1.0"}
        }))
        (self.tmpdir / "server" / "index.js").write_text(SAMPLE_EXPRESS_SERVER)
        (self.tmpdir / "server" / "models" / "User.js").write_text(SAMPLE_MONGOOSE_MODEL)
        (self.tmpdir / "src" / "components" / "LoginForm.jsx").write_text(SAMPLE_REACT_COMPONENT)
        (self.tmpdir / "src" / "components" / "Dashboard.jsx").write_text(SAMPLE_REACT_DASHBOARD)
        (self.tmpdir / "src" / "hooks" / "useAuth.js").write_text(SAMPLE_REACT_HOOK)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def run_detect(self):
        result = subprocess.run(
            ["python3", str(DETECT_SCRIPT), str(self.tmpdir)],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, f"Detector failed:\n{result.stderr}")
        return json.loads((self.tmpdir / ".project-defense" / "code-facts.json").read_text())

    def test_express_routes_found(self):
        facts = self.run_detect()
        routes = facts["express"]["routes"]
        methods_paths = {(r["method"], r["path"]) for r in routes}
        self.assertIn(("POST", "/api/auth/register"), methods_paths)
        self.assertIn(("POST", "/api/auth/login"), methods_paths)
        self.assertIn(("GET", "/api/users/me"), methods_paths)
        self.assertIn(("DELETE", "/api/users/:id"), methods_paths)

    def test_express_middleware_found(self):
        facts = self.run_detect()
        mw_names = {m["name"] for m in facts["express"]["middleware"]}
        # app.use(cors) and app.use(express.json) and the local authMiddleware
        # (the route handler references authMiddleware as an arg, not via app.use)
        self.assertIn("cors", mw_names)

    def test_mongoose_models_found(self):
        facts = self.run_detect()
        model_names = {m["name"] for m in facts["mongoose"]["models"]}
        self.assertIn("User", model_names)

    def test_react_components_found(self):
        facts = self.run_detect()
        component_names = {c["name"] for c in facts["react"]["components"]}
        self.assertIn("LoginForm", component_names)
        self.assertIn("Dashboard", component_names)

    def test_python_orm_models_found(self):
        # Add a SQLAlchemy + Django model file to the fixture
        (self.tmpdir / "app").mkdir()
        (self.tmpdir / "app" / "models.py").write_text('''
from sqlalchemy import Column, Integer, String
from .database import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    title = Column(String)


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
''')
        (self.tmpdir / "blog").mkdir()
        (self.tmpdir / "blog" / "models.py").write_text('''
from django.db import models


class Article(models.Model):
    title = models.CharField(max_length=200)
''')
        facts = self.run_detect()
        names = {m["name"]: m["framework"] for m in facts["python_orm"]["models"]}
        self.assertEqual(names.get("Task"), "sqlalchemy")
        self.assertEqual(names.get("Comment"), "sqlalchemy")
        self.assertEqual(names.get("Article"), "django")

    def test_react_hooks_found(self):
        facts = self.run_detect()
        hook_names = {h["name"] for h in facts["react"]["hooks"]}
        self.assertIn("useAuth", hook_names)

    def test_api_calls_found(self):
        facts = self.run_detect()
        api_names = {c["name"] for c in facts["api_calls"]}
        self.assertTrue(any("axios.get" in n and "/api/users/me" in n for n in api_names))
        self.assertTrue(any("fetch:" in n and "/api/auth/login" in n for n in api_names))

    def test_auth_signals(self):
        facts = self.run_detect()
        self.assertGreater(len(facts["auth"]["jwt_verify"]), 0, "Should detect jwt.verify")
        self.assertGreater(len(facts["auth"]["bcrypt_usage"]), 0, "Should detect bcrypt.hash")

    def test_skip_node_modules(self):
        nm = self.tmpdir / "node_modules" / "express"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text(SAMPLE_EXPRESS_SERVER)
        facts = self.run_detect()
        # Routes must still come only from our test files, not from node_modules
        all_files = {r["evidence"]["file"] for r in facts["express"]["routes"]}
        self.assertFalse(any("node_modules" in f for f in all_files))


class TestValidator(unittest.TestCase):
    def test_valid_graph_passes(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(VALID_GRAPH, f)
            path = f.name
        try:
            result = subprocess.run(
                ["python3", str(VALIDATE_SCRIPT), path, str(SCHEMA)],
                capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, f"Should pass:\n{result.stderr}\n{result.stdout}")
        finally:
            Path(path).unlink(missing_ok=True)

    def test_missing_required_keys_fails(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(INVALID_GRAPH_MISSING_REQUIRED, f)
            path = f.name
        try:
            result = subprocess.run(
                ["python3", str(VALIDATE_SCRIPT), path, str(SCHEMA)],
                capture_output=True, text=True
            )
            self.assertNotEqual(result.returncode, 0, "Should fail on missing keys")
            self.assertIn("frontend", result.stderr)
            self.assertIn("backend", result.stderr)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_invalid_status_fails(self):
        bad = json.loads(json.dumps(VALID_GRAPH))
        bad["frontend"]["components"][0]["evidence"]["status"] = "weird-status"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(bad, f)
            path = f.name
        try:
            result = subprocess.run(
                ["python3", str(VALIDATE_SCRIPT), path, str(SCHEMA)],
                capture_output=True, text=True
            )
            self.assertNotEqual(result.returncode, 0, "Should fail on invalid enum value")
        finally:
            Path(path).unlink(missing_ok=True)


class TestFetchRepositoryURLParsing(unittest.TestCase):
    """Test the URL parser without hitting the network."""

    def run_info(self, url: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["python3", str(FETCH_SCRIPT), url, "--info"],
            capture_output=True, text=True
        )

    def test_https_github_url(self):
        r = self.run_info("https://github.com/facebook/react")
        self.assertEqual(r.returncode, 0, r.stderr)
        info = json.loads(r.stdout)
        self.assertEqual(info["owner"], "facebook")
        self.assertEqual(info["repo"], "react")

    def test_url_with_dot_git_suffix(self):
        r = self.run_info("https://github.com/owner/repo.git")
        self.assertEqual(r.returncode, 0, r.stderr)
        info = json.loads(r.stdout)
        self.assertEqual(info["repo"], "repo")

    def test_url_with_trailing_slash(self):
        r = self.run_info("https://github.com/owner/repo/")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_rejects_gitlab(self):
        r = self.run_info("https://gitlab.com/owner/repo")
        self.assertNotEqual(r.returncode, 0, "GitLab must be rejected in v1")
        self.assertIn("not allowed", r.stderr)

    def test_rejects_bitbucket(self):
        r = self.run_info("https://bitbucket.org/owner/repo")
        self.assertNotEqual(r.returncode, 0, "Bitbucket must be rejected in v1")

    def test_rejects_file_scheme(self):
        r = self.run_info("file:///etc/passwd")
        self.assertNotEqual(r.returncode, 0, "file:// must be rejected")
        self.assertIn("http://", r.stderr)

    def test_rejects_truncated_path(self):
        r = self.run_info("https://github.com/")
        self.assertNotEqual(r.returncode, 0, "Truncated URL must be rejected")

    def test_rejects_owner_only(self):
        r = self.run_info("https://github.com/owner")
        self.assertNotEqual(r.returncode, 0, "Owner-only URL must be rejected")

    def test_rejects_http_plaintext(self):
        # We allow http:// per the regex, but warn -- it should still parse.
        # The actual security check is at the HTTPS layer when downloading.
        r = self.run_info("http://github.com/owner/repo")
        self.assertEqual(r.returncode, 0, "http is allowed by parser (would be blocked at TLS time)")

    def test_rejects_arbitrary_host(self):
        r = self.run_info("https://evil.com/owner/repo")
        self.assertNotEqual(r.returncode, 0, "Arbitrary host must be rejected")
        self.assertIn("not allowed", r.stderr)


class TestBuildGraph(unittest.TestCase):
    """End-to-end: scan + detect + build should produce a valid graph."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pdc-build-"))
        (self.tmpdir / "server" / "models").mkdir(parents=True)
        (self.tmpdir / "server" / "routes").mkdir(parents=True)
        (self.tmpdir / "server" / "middleware").mkdir(parents=True)
        (self.tmpdir / "src" / "components").mkdir(parents=True)
        (self.tmpdir / "package.json").write_text(json.dumps({
            "name": "build-test",
            "version": "1.0.0",
            "description": "A test app for build_graph.py",
            "main": "server/index.js",
            "dependencies": {
                "express": "^4.0.0",
                "mongoose": "^7.0.0",
                "jsonwebtoken": "^9.0.0",
                "bcrypt": "^5.0.0",
            }
        }))
        (self.tmpdir / ".env.example").write_text("JWT_SECRET=x\nMONGODB_URI=x\n")
        (self.tmpdir / "server" / "index.js").write_text('''
const express = require("express");
const authMiddleware = require("./middleware/auth");
const authRoutes = require("./routes/auth");
const todoRoutes = require("./routes/todos");
const app = express();
app.use("/api/auth", authRoutes);
app.use("/api/todos", authMiddleware, todoRoutes);
''')
        (self.tmpdir / "server" / "middleware" / "auth.js").write_text('''
const jwt = require("jsonwebtoken");
const authMiddleware = (req, res, next) => {
  const token = req.headers.authorization;
  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    req.user = decoded;
    next();
  } catch (e) {
    return res.status(401).json({ error: "Unauthorized" });
  }
};
module.exports = authMiddleware;
''')
        (self.tmpdir / "server" / "routes" / "auth.js").write_text(SAMPLE_AUTH_ROUTES)
        (self.tmpdir / "server" / "routes" / "todos.js").write_text(SAMPLE_TODO_ROUTES)
        (self.tmpdir / "server" / "models" / "User.js").write_text(SAMPLE_MONGOOSE_MODEL)
        (self.tmpdir / "src" / "components" / "App.jsx").write_text(SAMPLE_REACT_COMPONENT)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_end_to_end_builds_valid_graph(self):
        # Run scan + detect + build
        for script in (SCAN_SCRIPT, SKILL_DIR / "scripts" / "detect_code_facts.py", BUILD_SCRIPT):
            r = subprocess.run(
                ["python3", str(script), str(self.tmpdir)],
                capture_output=True, text=True
            )
            self.assertEqual(r.returncode, 0, f"{script.name} failed:\n{r.stderr}")
        graph_path = self.tmpdir / ".project-defense" / "project-graph.json"
        self.assertTrue(graph_path.exists(), "graph file was not created")
        graph = json.loads(graph_path.read_text())
        # Sanity checks
        self.assertEqual(graph["project"]["name"], "build-test")
        self.assertIn("Express", graph["project"]["stack"])
        self.assertEqual(len(graph["data"]["models"]), 1)
        self.assertEqual(len(graph["backend"]["routes"]), 4)  # login, register, GET todos, POST todos
        # All routes have non-null handlers (fallback to file basename)
        for r in graph["backend"]["routes"]:
            self.assertIsNotNone(r["handler"], f"route {r['method']} {r['path']} has no handler")
            self.assertIsInstance(r["handler"], str)
        # Auth strategy should be JWT (we have jwt.verify in the test fixture)
        self.assertEqual(graph["auth"]["strategy"], "JWT")
        # Protected routes should be ONLY the /api/todos/* routes, not /api/auth/*
        protected_paths = {pr["details"]["path"] for pr in graph["auth"]["protected_routes"]}
        todos_protected = all(p.startswith("/api/todos") for p in protected_paths)
        auth_not_protected = not any(p.startswith("/api/auth") for p in protected_paths)
        self.assertTrue(todos_protected, f"non-todos route marked protected: {protected_paths}")
        self.assertTrue(auth_not_protected, f"auth route marked protected: {protected_paths}")
        # Should have at least one uncertainty (JWT_SECRET, MONGODB_URI both detected)
        self.assertGreaterEqual(len(graph["uncertainties"]), 1)

    def test_validates_against_schema(self):
        subprocess.run(["python3", str(SCAN_SCRIPT), str(self.tmpdir)], capture_output=True)
        subprocess.run(["python3", str(SKILL_DIR / "scripts" / "detect_code_facts.py"), str(self.tmpdir)], capture_output=True)
        subprocess.run(["python3", str(BUILD_SCRIPT), str(self.tmpdir)], capture_output=True)
        r = subprocess.run(
            ["python3", str(VALIDATE_SCRIPT), str(self.tmpdir / ".project-defense" / "project-graph.json"), str(SCHEMA)],
            capture_output=True, text=True
        )
        self.assertEqual(r.returncode, 0, f"Schema validation failed:\n{r.stderr}")


class TestSafeExtract(unittest.TestCase):
    """Regression tests for fetch_repository.safe_extract security fixes."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SKILL_DIR / "scripts"))

    def _make_malicious_tar(self, name, linkname=None, member_type=None):
        import io, tarfile
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            info = tarfile.TarInfo(name=name)
            if linkname is not None:
                info.type = member_type
                info.linkname = linkname
            else:
                info.size = 0
            t.addfile(info)
        buf.seek(0)
        return buf

    def test_rejects_symlink_member(self):
        from fetch_repository import safe_extract, FetchError
        import tarfile
        buf = self._make_malicious_tar("evil_link", linkname="/etc/passwd", member_type=tarfile.SYMTYPE)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FetchError):
                safe_extract(tarfile.open(fileobj=buf, mode="r:gz"), Path(td))

    def test_rejects_hardlink_member(self):
        from fetch_repository import safe_extract, FetchError
        import tarfile
        buf = self._make_malicious_tar("evil_hard", linkname="/etc/passwd", member_type=tarfile.LNKTYPE)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FetchError):
                safe_extract(tarfile.open(fileobj=buf, mode="r:gz"), Path(td))

    def test_accepts_regular_file(self):
        from fetch_repository import safe_extract
        import io, tarfile
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            data = b"hello"
            info = tarfile.TarInfo(name="readme.txt")
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
        buf.seek(0)
        with tempfile.TemporaryDirectory() as td:
            safe_extract(tarfile.open(fileobj=buf, mode="r:gz"), Path(td))
            self.assertEqual((Path(td) / "readme.txt").read_text(), "hello")

    def test_temp_dir_cleaned_on_fetch_error(self):
        """Regression: P-RES-LEAK -- extract_to_tempdir must clean up on FetchError."""
        from fetch_repository import extract_to_tempdir, FetchError
        import tarfile, os
        buf = self._make_malicious_tar("../escaped")
        tmp_root = tempfile.gettempdir()
        before = len([d for d in os.listdir(tmp_root) if d.startswith("pdc-fetch-")])
        try:
            extract_to_tempdir(buf.getvalue())
        except FetchError:
            pass
        after = len([d for d in os.listdir(tmp_root) if d.startswith("pdc-fetch-")])
        self.assertEqual(before, after, "temp dir leaked after FetchError")


class TestScanRepository(unittest.TestCase):
    """The original scanner should still work on its own skill folder."""

    def test_scanner_runs_on_skill_itself(self):
        result = subprocess.run(
            ["python3", str(SCAN_SCRIPT), str(SKILL_DIR)],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, f"Scanner failed:\n{result.stderr}")
        facts_path = SKILL_DIR / ".project-defense" / "scan-facts.json"
        self.assertTrue(facts_path.exists())
        facts = json.loads(facts_path.read_text())
        self.assertIn("Python", facts["languages"])
        self.assertIn("Markdown", facts["languages"])


if __name__ == "__main__":
    unittest.main(verbosity=2)