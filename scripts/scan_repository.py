#!/usr/bin/env python3
"""
scan_repository.py -- Static analysis scanner for project-defense-skill.

Run from the repository root. Outputs JSON to .project-defense/scan-facts.json.
Stdlib only (Python 3.8+), no external dependencies.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------


EXTENSION_TO_LANGUAGE = {
    ".js": "JavaScript",
    ".jsx": "JavaScript (React)",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React)",
    ".py": "Python",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".cpp": "C++",
    ".c": "C",
    ".cs": "C#",
    ".php": "PHP",
    ".rb": "Ruby",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".md": "Markdown",
    ".sh": "Shell",
    ".sql": "SQL",
    ".graphql": "GraphQL",
    ".proto": "Protobuf",
    ".dockerfile": "Dockerfile",
}

MANIFEST_FILES = {
    "package.json": "npm",
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "requirements.txt": "pip",
    "pyproject.toml": "pip/poetry",
    "Pipfile": "pipenv",
    "poetry.lock": "poetry",
    "Cargo.toml": "cargo",
    "go.mod": "go modules",
    "pom.xml": "maven",
    "build.gradle": "gradle",
    "build.gradle.kts": "gradle (kotlin)",
    "composer.json": "composer",
    "Gemfile": "bundler",
    "mix.exs": "mix",
}

CONFIG_FILES = [
    ".env.example",
    ".env.local",
    ".env.development",
    ".env.production",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Dockerfile",
    ".dockerignore",
    ".github/workflows",
    ".gitlab-ci.yml",
    ".circleci/config.yml",
    "Makefile",
    "justfile",
    "Taskfile.yml",
    "turbo.json",
    "nx.json",
]

TEST_DIR_PATTERNS = [
    "test", "tests", "__tests__", "spec", "specs", "e2e", "cypress", "playwright"
]

ENTRY_POINT_PATTERNS = [
    "index.js", "index.ts", "main.js", "main.ts", "app.js", "app.ts",
    "server.js", "server.ts", "main.py", "app.py", "manage.py",
    "src/main.tsx", "src/main.jsx", "src/index.tsx", "src/index.jsx",
    "entry.js", "entry.ts", "bootstrap.js", "bootstrap.ts",
]

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def read_text(path: Path, max_chars: int = 50000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except Exception:
        return ""


def find_files(root: Path, patterns: List[str], max_depth: int = 3) -> List[Path]:
    results = []
    for pattern in patterns:
        for p in root.rglob(pattern):
            try:
                if len(p.relative_to(root).parts) <= max_depth:
                    results.append(p)
            except ValueError:
                pass
    return sorted(set(results))


def count_languages(root: Path) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for ext, lang in EXTENSION_TO_LANGUAGE.items():
        files = list(root.rglob(f"*{ext}"))
        if files:
            counts[lang] = len(files)
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def get_folder_structure(root: Path, max_depth: int = 2) -> Dict[str, Any]:
    def walk(dir_path: Path, depth: int) -> Dict[str, Any]:
        if depth > max_depth:
            return {}
        result = {}
        try:
            for item in sorted(dir_path.iterdir()):
                if item.name.startswith(".") and item.name not in (".github", ".gitlab", ".vscode"):
                    continue
                if item.is_dir():
                    result[item.name + "/"] = walk(item, depth + 1)
                else:
                    result[item.name] = "file"
        except PermissionError:
            pass
        return result
    return walk(root, 0)


def parse_package_json(content: str) -> Dict[str, Any]:
    try:
        data = json.loads(content)
        return {
            "name": data.get("name"),
            "version": data.get("version"),
            "dependencies": list(data.get("dependencies", {}).keys()),
            "devDependencies": list(data.get("devDependencies", {}).keys()),
            "scripts": data.get("scripts", {}),
            "engines": data.get("engines"),
        }
    except json.JSONDecodeError:
        return {}


def parse_requirements_txt(content: str) -> List[str]:
    deps = []
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            deps.append(line.split("==")[0].split(">=")[0].split("<=")[0].strip())
    return deps


def detect_framework(deps: List[str], root: Path) -> Dict[str, Any]:
    result = {"frontend": [], "backend": [], "database": [], "testing": [], "other": []}
    dep_lower = [d.lower() for d in deps]

    # Frontend
    if any("react" in d for d in dep_lower):
        result["frontend"].append("React")
    if any("next" in d for d in dep_lower):
        result["frontend"].append("Next.js")
    if any("vue" in d for d in dep_lower):
        result["frontend"].append("Vue")
    if any("svelte" in d for d in dep_lower):
        result["frontend"].append("Svelte")
    if any("vite" in d for d in dep_lower):
        result["other"].append("Vite")
    if any("webpack" in d for d in dep_lower):
        result["other"].append("Webpack")

    # Backend
    if any("express" in d for d in dep_lower):
        result["backend"].append("Express")
    if any("fastify" in d for d in dep_lower):
        result["backend"].append("Fastify")
    if any("nestjs" in d or "@nestjs" in d for d in dep_lower):
        result["backend"].append("NestJS")
    if any("koa" in d for d in dep_lower):
        result["backend"].append("Koa")
    if any("flask" in d for d in dep_lower):
        result["backend"].append("Flask")
    if any("fastapi" in d for d in dep_lower):
        result["backend"].append("FastAPI")
    if any("django" in d for d in dep_lower):
        result["backend"].append("Django")

    # Database
    if any("mongoose" in d for d in dep_lower):
        result["database"].append("MongoDB (Mongoose)")
    if any("prisma" in d for d in dep_lower):
        result["database"].append("Prisma")
    if any("sequelize" in d for d in dep_lower):
        result["database"].append("Sequelize")
    if any("typeorm" in d for d in dep_lower):
        result["database"].append("TypeORM")
    if any("sqlalchemy" in d for d in dep_lower):
        result["database"].append("SQLAlchemy")
    if any("pg" == d or "pg@" in d for d in dep_lower):
        result["database"].append("PostgreSQL (pg)")
    if any("mysql" in d for d in dep_lower):
        result["database"].append("MySQL")

    # Testing
    if any("jest" in d for d in dep_lower):
        result["testing"].append("Jest")
    if any("vitest" in d for d in dep_lower):
        result["testing"].append("Vitest")
    if any("mocha" in d for d in dep_lower):
        result["testing"].append("Mocha")
    if any("cypress" in d for d in dep_lower):
        result["testing"].append("Cypress")
    if any("playwright" in d for d in dep_lower):
        result["testing"].append("Playwright")
    if any("pytest" in d for d in dep_lower):
        result["testing"].append("pytest")
    if any("supertest" in d for d in dep_lower):
        result["testing"].append("Supertest")

    # Auth
    if any("jsonwebtoken" in d or "jose" in d for d in dep_lower):
        result["other"].append("JWT")
    if any("bcrypt" in d for d in dep_lower):
        result["other"].append("bcrypt")
    if any("passport" in d for d in dep_lower):
        result["other"].append("Passport.js")

    return result


def extract_env_vars(content: str) -> List[str]:
    vars_found = set()
    for match in re.finditer(r"process\.env\.([A-Z_][A-Z0-9_]*)", content):
        vars_found.add(match.group(1))
    for match in re.finditer(r"os\.getenv\(['\"]([A-Z_][A-Z0-9_]*)['\"]\)", content):
        vars_found.add(match.group(1))
    for match in re.finditer(r"os\.environ\[['\"]([A-Z_][A-Z0-9_]*)['\"]\]", content):
        vars_found.add(match.group(1))
    return sorted(vars_found)


def scan_repository(root: Path) -> Dict[str, Any]:
    root = root.resolve()

    # Language detection
    languages = count_languages(root)

    # Manifests
    manifests = {}
    for manifest_name, manager in MANIFEST_FILES.items():
        for mf in root.rglob(manifest_name):
            if mf.is_file():
                content = read_text(mf)
                if manifest_name == "package.json":
                    manifests[str(mf.relative_to(root))] = {
                        "manager": manager,
                        "parsed": parse_package_json(content)
                    }
                elif manifest_name == "requirements.txt":
                    manifests[str(mf.relative_to(root))] = {
                        "manager": manager,
                        "parsed": {"dependencies": parse_requirements_txt(content)}
                    }
                else:
                    manifests[str(mf.relative_to(root))] = {
                        "manager": manager,
                        "parsed": {"raw_preview": content[:2000]}
                    }

    # All dependencies flat list
    all_deps = []
    for m in manifests.values():
        p = m.get("parsed", {})
        if "dependencies" in p:
            all_deps.extend(p["dependencies"])
        if "devDependencies" in p:
            all_deps.extend(p["devDependencies"])

    # Framework detection
    frameworks = detect_framework(all_deps, root)

    # Config files
    config_files = []
    for pattern in CONFIG_FILES:
        for cf in root.rglob(pattern):
            if cf.is_file():
                config_files.append(str(cf.relative_to(root)))
            elif cf.is_dir():
                for f in cf.rglob("*"):
                    if f.is_file():
                        config_files.append(str(f.relative_to(root)))

    # Test directories
    test_dirs = []
    for pattern in TEST_DIR_PATTERNS:
        for d in root.rglob(pattern):
            if d.is_dir():
                test_dirs.append(str(d.relative_to(root)))

    # Entry points
    entry_points = []
    for pattern in ENTRY_POINT_PATTERNS:
        for ep in root.rglob(pattern):
            if ep.is_file():
                entry_points.append(str(ep.relative_to(root)))

    # README
    readme_path = None
    for r in root.rglob("README*"):
        if r.is_file():
            readme_path = str(r.relative_to(root))
            break

    # Env vars from code
    env_vars = set()
    for ext in [".js", ".ts", ".jsx", ".tsx", ".py"]:
        for f in root.rglob(f"*{ext}"):
            if f.is_file():
                content = read_text(f)
                env_vars.update(extract_env_vars(content))

    # Run commands from package.json
    run_commands = {}
    for m in manifests.values():
        if m.get("manager") == "npm":
            scripts = m.get("parsed", {}).get("scripts", {})
            for k, v in scripts.items():
                run_commands[k] = v

    # Also check Makefile, justfile, etc.
    for cf in config_files:
        if cf.endswith(("Makefile", "justfile", "Taskfile.yml")):
            p = root / cf
            content = read_text(p)
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and ":" in line and not line.startswith("\t"):
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        run_commands[f"{cf}:{parts[0].strip()}"] = parts[1].strip()

    return {
        "repo_root": str(root),
        "folder_structure": get_folder_structure(root),
        "languages": languages,
        "dependency_manifests": manifests,
        "frameworks": frameworks,
        "readme_path": readme_path,
        "test_dirs": sorted(set(test_dirs)),
        "config_files": sorted(set(config_files)),
        "entry_points": sorted(set(entry_points)),
        "env_vars": sorted(env_vars),
        "run_commands": run_commands,
    }


def main():
    if len(sys.argv) < 2:
        repo_root = Path.cwd()
    else:
        repo_root = Path(sys.argv[1]).resolve()

    if not repo_root.exists():
        print(f"Error: {repo_root} does not exist", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {repo_root}...")
    facts = scan_repository(repo_root)

    output_dir = repo_root / ".project-defense"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "scan-facts.json"
    output_file.write_text(json.dumps(facts, indent=2))
    print(f"Written to {output_file}")

    # Summary
    print(f"\nLanguages: {', '.join(f'{k}({v})' for k,v in facts['languages'].items())}")
    print(f"Frameworks: {facts['frameworks']}")
    print(f"Entry points: {facts['entry_points'][:5]}")
    print(f"Env vars found: {len(facts['env_vars'])}")
    print(f"Test dirs: {facts['test_dirs'][:5]}")


if __name__ == "__main__":
    main()