# Changelog

All notable changes to the project-defense-skill are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Route extraction for four more frameworks.** `detect_code_facts.py` now finds routes in FastAPI/Flask (decorators, `APIRouter(prefix=...)`), Django (`path()`/`re_path()` with `include()` chains resolved into full paths, DRF `router.register(...)` expanded into its real actions) and Next.js (`app/api/**/route.ts` exports, `pages/api/**` method branches). Previously only Express was recognised, so a Django, FastAPI or Next.js project produced no routes at all and its question bank collapsed to 5-7 generic questions. Now: Django 5 -> 9, FastAPI 6 -> 10, Next.js 7 -> 9, and each with project-specific questions instead of filler.
- **Protected-route detection per framework.** FastAPI `Depends(get_current_user)` and DRF `permission_classes = [IsAuthenticated]` now mark routes as protected, joining Express mount prefixes. Django example: 12 of 15 routes.
- **Python and delegated auth signals.** jose/PyJWT, passlib/bcrypt, Django `authenticate`/`login`/`@login_required`, DRF permission classes, and JS providers (Supabase SSR, NextAuth/Auth.js) are all read, so `auth.strategy` is no longer `other` for those stacks (delegated providers resolve to `cookie`).
- **Auth-flow and frontend/backend-contract questions.** When protected routes exist, the bank asks how a request proves who the caller is (guard named). When the frontend calls endpoints, it asks to trace one call end to end and to name any call with no matching route.
- **`tests/test_framework_detection.py`** (18 tests) pinning every detector above, plus feature resolution, challenge relocation and coding-question grouping.

### Changed
- **One coding question per resource, not per route.** A DRF viewset serving six verbs produced six near-identical questions; routes are now grouped by resource (16 -> 4 coding questions on the Django example) and the question names the sibling methods, so nothing in the graph goes unmentioned.
- **Practice challenges relocate to the defining file.** `--feature PostViewSet.destroy` used to resolve to `urls.py` and refuse ("the starter would be identical"); `generate_challenge.py` now finds the file that defines the handler (class or function) and builds the exercise there.
- Failure-scenario questions rephrased so any risk sentence reads correctly ("Your project has this known weakness: X. If it were exercised in production...") instead of splicing text into "what happens when ...?".
- The generic `auth` walkthrough question is skipped when the dedicated auth-flow question is generated, so the same ground is not covered twice.

## [0.5.0] - 2026-11-25

First tagged release of the verification loop: the analysis now carries edges and
freshness, every generated question is gradeable, and practice mode is separate
from the answer it is testing. 109 tests.

### Added

**Analysis**
- `scripts/build_graph.py` -- merges the scan and the code facts into a
  schema-valid project graph.
- File-level edges in the graph (`relationships`): `imports` (resolved from
  `import` / `require` / `from ... import`, internal files only), `tested_by`
  (test matched to source by naming convention) and `protects` (middleware
  guarding a route prefix). Bounded to 500 edges, written in deterministic order.
  Without them, "what breaks if I delete this?" could not be answered from
  evidence.
- `analyzed_at`, `git_head` and `content_fingerprint` on the graph, so freshness
  is checkable instead of assumed.
- `scripts/check_graph_freshness.py` -- compares the graph against HEAD and
  reports `commits_behind` (exit 1 when stale, 2 when the graph is missing). Falls
  back to the content fingerprint when the repository has no git history.
- `scripts/path_filters.py` -- shared noise-directory list and
  `.project-defenseignore` loader (a gitignore subset with `!` negation) used by
  the scanner and the detector.
- `.project-defenseignore` support: generated or vendored paths can be excluded
  from the analysis without editing the skill.
- Python ORM detection in `scripts/detect_code_facts.py` -- finds SQLAlchemy and
  Django models.

**Assessment**
- `scripts/plan_review.py` -- spaced-retrieval planner. Turns existing sessions
  into a review schedule on a Leitner ladder (1, 3, 7, 16, 35 days), pulls weak
  questions (mean concept score < 2/3) back to a shorter interval, marks
  never-answered questions due immediately, and interleaves categories so practice
  forces recall instead of pattern-matching. Deterministic for a given `--today`;
  `--write` emits `.project-defense/review-plan.md`.
- Deletion-test questions in the question bank ("If X were deleted entirely, what
  would break and what would have to be reimplemented elsewhere?"), citing the
  importers the graph found, plus `rubrics/explanation-module-depth-v1.json`,
  which grades call sites, reimplementation cost, interface surface and a depth
  verdict.
- Diagnosis questions ("a symptom is reported; how would you find the cause?")
  plus `rubrics/failure-diagnosis-v1.json`, scored on the discipline: a
  red-capable reproduction loop, minimisation, ranked falsifiable hypotheses, one
  variable at a time, and a regression test at a real seam.
- Category fallback rubrics -- `explanation-generic-v1`, `failure-generic-v1`,
  `tradeoff-generic-v1`, `coding-generic-v1` -- so no generated question ships
  ungradeable.

**Practice**
- Challenge `explainer.md` -- objective, what to read first, definition of done,
  how the work is judged, hints.
- `solution/` in every challenge: a reference implementation written beside the
  starter and never copied into `workspace/`. `run_checks.py` reports its path
  only once every check passes.

**Repository**
- `SCOPE.md` -- what the skill is, what it is deliberately not (explainer,
  linter, test generator, editor, oracle), the bar a change must clear (observed
  failure + fits the constraints), and the already-decided non-goals.
- `scripts/check_docs.py` -- documentation and wiring lint for the skill itself:
  SKILL.md frontmatter, every relative markdown link, every `scripts/` /
  `templates/` / `rubrics/` path named in prose, every script mentioned somewhere
  (dead wiring), unique rubric ids, and score weights that match
  `score_report.CATEGORY_WEIGHTS`.
- `templates/glossary-document.md` and Phase 5 item 4 (`docs/glossary.md`) -- one
  row per graph entity, defined in domain language without naming its technology,
  with a verified/assumed status, a words-to-avoid table, and a drift log. The
  glossary is the terminology authority for the later phases.
- `templates/data-flow-document.md` and `templates/core-logic-document.md` --
  templates for the two generated docs that were missing.
- `examples/example-todo-app/`, `examples/example-django-blog/`,
  `examples/example-fastapi-tasks/`, `examples/example-nextjs-todo/` --
  worked-example projects for dry-running the workflow, plus `examples/README.md`
  comparing them.
- `SECURITY.md` -- the privacy and safety contract (was in README only).
- `CONTRIBUTING.md` -- how to add detectors, templates or examples.
- `.gitignore`, `CHANGELOG.md`, and a GitHub Actions workflow
  (`.github/workflows/test.yml`).
- `tests/test_robustness.py` (27 tests) and `tests/test_review_docs.py`
  (17 tests), plus security regression tests in `tests/test_skill.py`
  (symlink/hardlink rejection, regular-file acceptance, temp dir cleanup).

### Changed
- Scanning walks the tree once with a pruned, deterministically sorted walk
  instead of repeated `rglob` calls.
- Rubric selection supports several fallbacks per category: a topic-bearing
  fallback (e.g. module depth) applies only when its keywords appear in the
  question text, otherwise the topic-less generic fallback wins. Previously only
  the first rubric loaded for a category could ever be selected.
- Review rounds in Phase 4: every uncertain item is labelled a **fact** (the agent
  answers it from the code) or a **decision** (the user's), and all independent
  decisions are asked in one numbered round with a recommended answer instead of
  one question per turn.
- `assess.py answer` records `answered_at` per question (optional in the schema)
  so the review planner has real attempt dates; `assess.py finish` reports
  `score_reliability` (`agent-scored` / `mixed` / `heuristic-only`) and warns on
  stderr when a score came from the keyword fallback, so a fallback number is
  never presented as a verdict.
- `score_report.py` output gains `scored_count`, `heuristic_scored` and `unscored`
  per category (inside the free-form `categories` object, so the session schema is
  unchanged).
- The documented score weights now match the scorer, and `check_docs.py` fails if
  they drift. The Reflection round is documented as unweighted: self-assessment
  moves the number without measuring knowledge.
- Phase 3 instructions direct the agent to run `build_graph.py` instead of
  hand-merging the two scan outputs.
- `detect_code_facts.py`: removed a dead duplicate function, added a JS-keyword
  filter for handler extraction, applied mount prefixes to route detection
  (including the 3-argument `app.use('/api/foo', mw, router)` form).
- `build_graph.py`: the protected-routes heuristic excludes router mounts (names
  ending in `Routes`) so only genuinely middleware-protected paths are flagged.
- `SKILL.md` description shortened from 207 to 70 characters to fit the SKILL.md
  spec.

### Fixed
- **Scanner read dependency trees.** `scan_repository.py` had no skip list, so
  `node_modules` (and `dist`, `build`, `venv`, `.git`) were walked as project
  source. A dependency's `package.json` could make React or MongoDB appear in the
  detected stack, dependency entry points appeared in `entry_points`, and env vars
  were harvested from third-party code.
- **Practice mode leaked the solution for JS/TS targets.** `_stub_function_body`
  only recognised Python `def`, so a `.jsx` challenge shipped the original
  implementation as its own starter file. JS/TS/JSX/TSX bodies are now stubbed by
  brace matching that skips strings, template literals and comments; Jest-style
  test skeletons are generated; and the syntax check matches the file type
  (Python AST, `node --check`, or a structural check for JSX/TSX).
- **Callbacks were not stubbed, and nested functions truncated the file.** Arrow
  and inline callbacks (`app.get("/x", (req, res) => {...})`) have no declaration
  to match, so such a file still shipped verbatim; and replacing an inner body
  shifted the offsets of the enclosing span, cutting the file off at its closing
  brace. The stubber now keeps only the outermost spans and stubs callback bodies,
  with a guard that refuses to write a starter identical to the source.
- **Unknown features produced a fabricated challenge.** `--feature` matched only
  an entry's `name`, so a route path or file path fell back to a synthetic stub --
  for `server/index.js` that produced `def server/index.js():`, an unsolvable
  exercise with a syntax error. Matching now covers name, method, path, handler,
  details and evidence file, and an unmatched feature exits with the list of
  available features.
- **Python 3.8 was not actually supported.** `dict | None` annotations failed at
  import time on 3.8/3.9 despite the documented floor. Replaced with
  `Optional[...]`; a regression test forbids PEP 604 unions in `scripts/`.
- **Unscored answers were counted as zero.** `score_report.py` added a question to
  its category denominator even when no rubric had graded it, collapsing a session
  to ~0.05 after a decent answer. Unscored questions are now reported separately
  and excluded from the score.
- **Only 3 of 17 generated questions had a rubric.** Rubrics were matched by
  `question_id` alone, so `q-e001` received an authentication rubric no matter what
  it asked. Rubrics may now declare `category` and `topic`.
- **Guided mode could never show a hint.** `assess.py` read `rubric["hints"]` but
  `rubric.schema.json` had `additionalProperties: false` without a `hints`
  property, so hints were impossible to author.
- **Keyword scoring awarded a point for length.** `_score_answer` gave a point to
  any answer over 20 characters. It now requires concept overlap, uses a
  5-character stem match, and tags its output `scored_by: heuristic`.
- **`coding_results` were discarded.** `assess.py` appended them to a dict that was
  then dropped, so coding attempts never reached the session file.
- **CI ran one of six test files.** The workflow invoked `tests/test_skill.py`
  only, which is how several of the defects above shipped. CI now runs full
  discovery on Python 3.8/3.10/3.12 (ubuntu) plus 3.12 on Windows, smoke-tests all
  four examples, validates every rubric against the schema, and runs
  `check_docs.py`.
- `handler: "async"` was emitted as a route handler when the actual handler was an
  inline arrow function.
- `/api/auth/*` routes were incorrectly marked as protected (they are the auth
  endpoints themselves, not protected by auth).
- `app.use(cors())` was missed by the middleware detector (the regex did not allow
  a trailing `()`).
- Auth routes showed `/register` and `/login` instead of `/api/auth/register` and
  `/api/auth/login` (the mount prefix was not applied).
- The React component test only matched `export default function` and missed
  `const X = () =>`.

### Security
- **FIXED: CVE-2007-4559-style tarfile symlink/hardlink bypass in
  `fetch_repository.py`.** `safe_extract()` now rejects any tar member whose type
  is not `REGTYPE`, `AREGTYPE` or `DIRTYPE`. Previously a public GitHub repo owner
  could read any file the user could read by committing a symlink whose target
  pointed outside the repo. Found during a security-audit run on 2026-10-16.
- **FIXED: temp dir leak on `safe_extract` rejection.** `extract_to_tempdir` uses
  `try/except BaseException` so the temp dir is cleaned up on any failure path
  (FetchError, OSError, KeyboardInterrupt), not just `tarfile.TarError`.
- **REMOVED: unused `READ_TIMEOUT` constant.** `urlopen`'s `timeout` kwarg only
  bounds the connect phase; the docstring now documents the actual behaviour.
- **Defense in depth:** on Python 3.12+, `safe_extract` passes `filter="data"` to
  `extractall` as a second line of defence against member types the manual check
  might miss.

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
