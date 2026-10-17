# Changelog

All notable changes to the project-defense-skill are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `scripts/build_graph.py` -- merges scan + code-facts into a schema-valid project graph
- `templates/data-flow-document.md` and `templates/core-logic-document.md` -- templates for the two missing generated docs
- `examples/example-todo-app/` -- worked-example React + Express + MongoDB project for dry-running the workflow
- `examples/example-django-blog/` -- worked-example Django + DRF + PostgreSQL project
- `examples/example-fastapi-tasks/` -- worked-example FastAPI + SQLAlchemy + SQLite project
- `examples/example-nextjs-todo/` -- worked-example Next.js 14 + Supabase project
- `examples/README.md` -- comparison table of all examples, what each tests
- Python ORM detector in `scripts/detect_code_facts.py` -- finds SQLAlchemy and Django models
- `SECURITY.md` -- full privacy and safety contract (was in README only)
- `.gitignore` -- Python, `__pycache__/`, `.project-defense/`, editors
- GitHub Actions CI workflow (`.github/workflows/test.yml`)
- `CONTRIBUTING.md` -- how to add detectors, templates, or new examples
- `CHANGELOG.md` -- this file
- Security regression tests in `tests/test_skill.py` -- symlink/hardlink rejection, regular-file acceptance, temp dir cleanup

### Changed
- `SKILL.md` description shortened to 70 chars (from 207) to fit the SKILL.md spec's 60-char limit, while preserving the core trigger meaning
- `scripts/detect_code_facts.py` -- removed dead duplicate function, added JS-keyword filter for handler extraction
- `scripts/detect_code_facts.py` -- route detection now applies mount prefixes (handles `app.use('/api/foo', router)` and the 3-arg `app.use('/api/foo', mw, router)` form)
- `scripts/build_graph.py` -- protected-routes heuristic now excludes router mounts (name ending in `Routes`) so it only flags middleware-protected paths
- Phase 3 instructions now direct the agent to run `build_graph.py` instead of hand-merging the two scan outputs

### Security
- **FIXED: CVE-2007-4559-style tarfile symlink/hardlink bypass in `fetch_repository.py`.** `safe_extract()` now rejects any tar member whose type is not `REGTYPE`, `AREGTYPE`, or `DIRTYPE` (lines 150-159). Previously, a public GitHub repo owner could read any file the user could read by committing a symlink whose target pointed outside the repo. Discovered during a Cloudflare security-audit-skill run on 2026-10-16. See `~/security-audit-skill/project-defense-coach/run-1/REPORT.md` for the full audit.
- **FIXED: temp dir leak on `safe_extract` rejection.** `extract_to_tempdir` now uses a `try/except BaseException` block so the temp dir is cleaned up on any failure path (FetchError, OSError, KeyboardInterrupt), not just `tarfile.TarError`.
- **REMOVED: unused `READ_TIMEOUT` constant.** The constant was declared but never used; `urlopen`'s `timeout` kwarg only bounds the connect phase, not the read phase. The constant is removed and the docstring documents the actual behavior.
- **Defense in depth:** on Python 3.12+, `safe_extract` now passes `filter="data"` to `extractall` as a second line of defense against member types the manual check might miss.

### Fixed
- `handler: "async"` was emitted as a route handler when the actual handler was an inline arrow function
- `/api/auth/*` routes were incorrectly marked as protected (they're the auth endpoints themselves, not protected by auth)
- `app.use(cors())` was missed by the middleware detector (regex didn't allow trailing `()`)
- Auth routes showed `/register` and `/login` instead of `/api/auth/register` and `/api/auth/login` (mount prefix wasn't applied)
- Test for React components only matched `export default function`, missed `const X = () =>`

## [0.1.0] - 2026-10-16

### Added
- Initial skill structure (`SKILL.md`, `README.md`, `LICENSE`)
- Three instruction files: `00-workflow.md` (master reference), `01-analyze-and-verify.md` (phases 1-4), `02-generate-docs.md` (phases 5-10)
- `scripts/scan_repository.py` -- top-level repo scanner (file tree, languages, dependency manifests, env vars)
- `templates/project-graph.schema.json` -- JSON Schema (Draft-07) for the project graph
- `templates/architecture-document.md` -- template for `docs/architecture-overview.md`

### Notes
- v1 supports React + Node/Express + MongoDB. Other stacks are experimental.
- Public repos only in v1 (no private-repo token support).
