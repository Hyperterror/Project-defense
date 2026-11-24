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

# Local import so the shared filter works from any cwd.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from path_filters import (  # noqa: E402
    is_ignored,
    is_noise_dir,
    load_ignore_patterns,
    walk_files,
    walk_source_files,
)


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


def count_languages(root: Path, patterns: Optional[List[str]] = None) -> Dict[str, int]:
    """Count files by language, ignoring dependencies, build output and .git."""
    counts: Dict[str, int] = {}
    for path in walk_files(root, patterns):
        lang = EXTENSION_TO_LANGUAGE.get(path.suffix.lower())
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def get_folder_structure(root: Path, max_depth: int = 2) -> Dict[str, Any]:
    def walk(dir_path: Path, depth: int) -> Dict[str, Any]:
        if depth > max_depth:
            return {}
        result = {}
        try:
            for item in sorted(dir_path.iterdir()):
                if item.is_dir():
                    if is_noise_dir(item.name):
                        continue
                    result[item.name + "/"] = walk(item, depth + 1)
                else:
                    if item.name.startswith(".") and item.name not in (".github", ".gitlab", ".vscode"):
                        continue
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


def _iter_dirs(root: Path, patterns: Optional[List[str]] = None) -> List[Path]:
    """List non-noise directories under root, honouring ignore patterns."""
    dirs: List[Path] = []
    for dirpath, dirnames, _ in os.walk(str(root)):
        current = Path(dirpath)
        dirnames[:] = [d for d in sorted(dirnames) if not is_noise_dir(d)]
        for name in dirnames:
            full = current / name
            try:
                if patterns and is_ignored(full.relative_to(root), patterns):
                    continue
            except ValueError:
                continue
            dirs.append(full)
    return dirs


def _config_file_matches(rel_posix: str, name: str) -> bool:
    for pattern in CONFIG_FILES:
        if "/" in pattern:
            if rel_posix == pattern or rel_posix.startswith(pattern + "/"):
                return True
        elif name == pattern:
            return True
    return False


def _entry_point_matches(rel_posix: str) -> bool:
    for pattern in ENTRY_POINT_PATTERNS:
        if rel_posix == pattern or rel_posix.endswith("/" + pattern):
            return True
    return False


def scan_repository(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    ignore_patterns = load_ignore_patterns(root)

    # Language detection
    languages = count_languages(root, ignore_patterns)

    # Manifests -- only the project's own, never a dependency's.
    manifests = {}
    for path in walk_files(root, ignore_patterns):
        manifest_name = path.name
        manager = MANIFEST_FILES.get(manifest_name)
        if manager is None:
            continue
        content = read_text(path)
        rel = str(path.relative_to(root))
        if manifest_name == "package.json":
            manifests[rel] = {
                "manager": manager,
                "parsed": parse_package_json(content)
            }
        elif manifest_name == "requirements.txt":
            manifests[rel] = {
                "manager": manager,
                "parsed": {"dependencies": parse_requirements_txt(content)}
            }
        else:
            manifests[rel] = {
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
    for path in walk_files(root, ignore_patterns):
        rel_posix = path.relative_to(root).as_posix()
        if _config_file_matches(rel_posix, path.name):
            config_files.append(str(path.relative_to(root)))

    # Test directories
    test_dirs = []
    for d in _iter_dirs(root, ignore_patterns):
        if d.name in TEST_DIR_PATTERNS:
            test_dirs.append(str(d.relative_to(root)))

    # Entry points
    entry_points = []
    for path in walk_files(root, ignore_patterns):
        if _entry_point_matches(path.relative_to(root).as_posix()):
            entry_points.append(str(path.relative_to(root)))

    # README
    readme_path = None
    for path in walk_files(root, ignore_patterns):
        if path.name.upper().startswith("README"):
            readme_path = str(path.relative_to(root))
            break

    # Env vars from code
    env_vars = set()
    for path in walk_source_files(root, [".js", ".ts", ".jsx", ".tsx", ".py"], ignore_patterns):
        env_vars.update(extract_env_vars(read_text(path)))

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
        "ignore_patterns": ignore_patterns,
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