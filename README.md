# Project Defense Coach — Agent Skill

Turn your AI coding agent (Claude Code, Codex CLI, Antigravity, Kiro, etc.) into a
**project-defense coach**: it analyzes *your* repository, verifies its understanding
with you, then generates documentation, diagrams, a personalized learning path,
project-specific interview questions, and runs a scored mock interview.

---

## What This Skill Does

1. **Analyzes your local repo** — file tree, stack, entry points, dependencies, tests
2. **Static analysis via script** — extracts routes, components, models, auth, API calls
3. **Builds a project graph** — machine-readable JSON with evidence for every claim
4. **Verification loop (the differentiator)** — you confirm/correct/flag uncertainties
   *before* any documentation is generated
5. **Generates 4 documents** — architecture overview, data flow, core logic, domain glossary
6. **Emits 3 Mermaid diagrams** — architecture, data flow, user flow (text, versionable)
7. **Creates a learning path** — 10 stages mapped to *your* project's actual features
8. **Builds a question bank** — explanation, failure scenarios, trade-offs, coding tasks, and deletion-test questions, each linked to a machine-readable rubric
9. **Runs a mock interview** — 7 segments, scored against rubrics (0–3 per concept)
10. **Schedules the review** — a spaced-retrieval plan says which questions to re-answer today, so recall survives past the interview
11. **Produces a readiness report** — score, strengths, gaps, prioritized next steps with file references

It also has two interactive coaching modes that build on the analyzed graph:

- **Practice Mode** — generates a coding challenge from your graph (function reconstruction, bug fix, or test writing), sets up an isolated workspace with starter files, coaches you with progressive hints, and runs manifest checks against your solution. Your original files are never modified.
- **Assessment Mode** — runs a structured assessment against the question bank, records every Q&A in a session file, scores each answer against its rubric, and produces a weighted overall score. Strict mode gives no hints; guided mode offers rubric hints when your score is low.
- **Review Mode** — `scripts/plan_review.py` reads your sessions and returns the questions that are due today, interleaved across categories and shortened for the concepts you scored below 2/3. Retrieval practice, not re-reading.

---

## Quick Start

The fastest way to install this skill into your AI coding agent is with the
[skills CLI](https://github.com/antfu/skills-cli) (the open agent-skills
package manager). It auto-detects your agent's skills directory and symlinks
the skill folder — no manual `cp` and **no fork required**. Users install
directly from the published repo.

```bash
# 1. Install the skill (interactively pick which agent(s) to target)
npx skills add Hyperterror/Project-defense

#    Pin the exact skill by name (matches the `name` in SKILL.md frontmatter)
#    and target a specific agent, non-interactively:
npx -y skills add Hyperterror/Project-defense --skill project-defense-skill --agent claude-code
npx -y skills add Hyperterror/Project-defense --skill project-defense-skill --agent antigravity
npx -y skills add Hyperterror/Project-defense --skill project-defense-skill --agent codex

#    Install to all detected agents at once:
npx skills add Hyperterror/Project-defense --all

#    Install globally (available across all your projects) instead of per-project:
npx skills add Hyperterror/Project-defense -g

# 2. Open your project in the agent and invoke the skill
#    "Run the project-defense skill on this repository"
#    or trigger it naturally: "understand my project", "audit this repo",
#    "prepare me to explain this project in an interview", "give me a challenge",
#    "assess me", "run a mock technical interview on my project"

# 3. The agent will:
#    - Run scripts/scan_repository.py
#    - Run scripts/detect_code_facts.py
#    - Build .project-defense/project-graph.json
#    - Present the verification report (Phase 4)
#    - After you confirm, generate all artifacts in .project-defense/
```

`Hyperterror/Project-defense` is the GitHub `owner/repo` where this skill is
published. The skills CLI finds the `SKILL.md` at the repo root and installs
the skill folder along with its `scripts/`, `templates/`, `rubrics/`, and
`instructions/`. You do not need to fork — install straight from the public repo.

### Use with a GitHub URL

```bash
# Fetch and analyze a public GitHub repo in one go:
LOCAL_PATH=$(python3 /path/to/skill/scripts/fetch_repository.py https://github.com/<owner>/<repo>)
python3 /path/to/skill/scripts/scan_repository.py "$LOCAL_PATH"
python3 /path/to/skill/scripts/detect_code_facts.py "$LOCAL_PATH"
# Temp dir is auto-cleaned on exit. Add --keep <dir> to persist.
```

The agent can also drive this end-to-end: when you paste a GitHub URL into
the agent chat, it will call `fetch_repository.py` first, then run the rest
of the workflow against the extracted copy.

**v1 limits:** public repos only, no private-repo token support yet.

---

## Supported Stacks

Two tiers. Both produce evidence for every claim; they differ in how much of the
framework's routing model the detector understands.

### Tier 1 — framework-aware

The detector knows how the framework composes routes, so it resolves prefixes,
mounts, routers and permission classes rather than pattern-matching each line.

| Stack | Routes | Auth | Models |
|-------|--------|------|--------|
| **React + Node/Express + MongoDB** | `app.get(...)`, `router.use(...)` mounts | JWT, bcrypt | Mongoose |
| **Django + DRF + PostgreSQL** | URLconf `path()` + `include()` chains, DRF routers | Django auth, DRF permissions | Django ORM |
| **FastAPI / Flask + SQL** | Decorators, `APIRouter(prefix=...)`, `Depends(...)` guards | jose/PyJWT, passlib | SQLAlchemy |
| **Next.js + Supabase** | `app/api/**/route.ts` and `pages/api/**` | Supabase SSR / NextAuth cookies | Supabase (client calls only) |

### Tier 2 — pattern packs

`scripts/detect_stack_generic.py` carries one pack per ecosystem. Each pack reads
that ecosystem's route, model and auth idioms and resolves the prefixes that
change a path: Gin `r.Group("/api")`, Rails `namespace :api do`,
Laravel `Route::prefix(...)`, ASP.NET `[Route("api/[controller]")]`.

| Ecosystem | Routes recognised | Models | Auth signals |
|---|---|---|---|
| **Go** | Gin/Echo/Chi/Fiber `r.GET(...)`, `http.HandleFunc`, `r.Method(...)` | GORM structs + field types | golang-jwt, bcrypt, argon2, auth middleware |
| **Ruby** | `routes.rb` verbs, `namespace`, `resources` (expanded), Sinatra | ActiveRecord models + associations | `has_secure_password`, Devise, `authenticate_user!` |
| **PHP** | Laravel `Route::get/post/...`, `apiResource` (expanded), prefix groups, Slim | Eloquent `$fillable` | Sanctum, Passport, `Hash::make`, `->middleware('auth')` |
| **Java** | Spring `@RequestMapping` + `@Get/PostMapping`, class-level prefixes | JPA `@Entity` | Spring Security, `@PreAuthorize`, `BCryptPasswordEncoder` |
| **C#** | ASP.NET `[Route]` + `[HttpGet]`, `[controller]` placeholder, minimal APIs | — | `[Authorize]`, JwtBearer, Identity |
| **Rust** | Axum `.route("/x", get(h))`, Actix `#[get("/x")]` | — | `jsonwebtoken`, argon2 |
| **Kotlin** | Ktor `get("/x") { }` | — | jwt, `authenticate(...)` |
| **Elixir** | Phoenix `get "/x", C, :action`, `resources` | Ecto `schema` | Guardian, Phoenix.Token |
| **Prisma** | — | `model X { ... }` with field types | — |

### Everything else

Any repository still gets an interview: the scan counts languages, reads the
manifests it understands, and generates questions about auth, failure diagnosis
and trade-offs. What it will not do is pretend. When no route and no model is
found, the graph records an uncertainty — *"Which framework serves this API, and
which file defines its first route?"* — the question bank warns that every
question is generic, and Phase 4 asks you before anything is written.

What stays manual everywhere: the service/controller layer, user flows and data
flows. The agent marks those UNVERIFIED and asks you rather than inventing them.

---

## Artifacts Produced

All outputs go in `.project-defense/` at your repository root:

```
.project-defense/
├── scan-facts.json           # Raw scanner output
├── code-facts.json           # Raw detector output (routes, components, models, auth)
├── corrections.json          # User confirmations/corrections from the verification loop
├── project-graph.json        # Validated against templates/project-graph.schema.json
├── question-bank.json        # Machine-readable question bank (4 categories)
├── question-bank.md          # Human-readable question bank
├── docs/
│   ├── architecture-overview.md
│   ├── data-flow.md
│   ├── core-logic.md
│   └── glossary.md           # Domain vocabulary: entity -> how you define it in one sentence
├── diagrams/
│   ├── architecture.mmd      # Mermaid source (renders in GitHub, Notion, Obsidian...)
│   ├── data-flow.mmd
│   └── user-flow.mmd
├── challenges/
│   └── <challenge-id>/
│       ├── manifest.json     # Challenge definition (validated against challenge.schema.json)
│       ├── explainer.md      # Objective, definition of done, how the work is judged
│       ├── starter/          # Starter files (TODO stubs / seeded bugs / test skeletons)
│       ├── solution/         # Reference solution -- never copied into the workspace
│       ├── workspace/        # Isolated copy of allowed files for you to edit
│       ├── workspace.json    # Workspace metadata
│       └── result.json       # check run results (PASSED/FAILED/NOT_RUN/INFRASTRUCTURE_ERROR)
├── sessions/
│   ├── <session-id>.json     # Assessment/interview session (Q&A, scores)
│   └── <session-id>-score.json  # Weighted score report
├── learning-path.md
├── review-plan.md            # What to re-answer today, and why (spaced retrieval)
└── readiness-report.md
```

Rubric files live in `rubrics/` at the skill root and are referenced by the question bank via `rubric_id`.

---

## Prerequisites

- **Python 3.8+** (for `scripts/scan_repository.py` — stdlib only, no `pip install`)
- An agentic IDE/CLI that loads SKILL.md or equivalent (Claude Code, Codex CLI, Antigravity, Kiro, Cursor, etc.)
- Your project open in the agent

---

## Privacy & Safety

See [SECURITY.md](SECURITY.md) for the full privacy and safety contract. The short version:

- **Local only** — the skill analyzes only the folder you opened. No code leaves your machine.
- **GitHub URL mode (opt-in)** — when you give a URL, `fetch_repository.py` downloads a public repo as a tarball to a temp dir, scans it, and cleans up. The tarball is the only thing that leaves your machine. Private repos are not supported in v1.
- **No other network calls** — the scanner and detector scripts use stdlib only; they do not phone home.
- **Secrets avoided** — the scanner skips `.env`, `*.pem`, `*.key`, `id_rsa*`, `*.secret` files unless you explicitly ask.
- **No mutations outside `.project-defense/` and the temp fetch dir** — the skill never pushes code, deletes files, or installs packages on its own.
- **Review scripts before running** — `scripts/*.py` are short and well-commented, but please read them first. Don't run code on your machine you haven't read.

---

## File Structure

```
project-defense-skill/
├── SKILL.md                           # Entry point (this skill's manifest)
├── README.md                          # This file
├── SECURITY.md                        # Privacy and safety contract
├── LICENSE
├── instructions/
│   ├── 00-workflow.md                 # Master workflow reference (all 10 phases)
│   ├── 01-analyze-and-verify.md       # Phases 1-4 checklist (ingestion → verification)
│   └── 02-generate-docs.md            # Phases 5-10 checklist (docs → readiness)
├── scripts/
│   ├── path_filters.py                # Shared skip-list + .project-defenseignore rules used by scan and detect
│   ├── scan_repository.py             # Repo scanner (stdlib, Python 3.8+)
│   ├── detect_code_facts.py           # Stack-specific code detectors (routes, components, models...)
│   ├── build_graph.py                 # Merges scan + code-facts into schema-valid project-graph.json (+ session_identity, git_head, analyzed_at)
│   ├── validate_graph.py              # JSON Schema validator for project-graph.json
│   ├── check_graph_freshness.py       # Is the graph still at git HEAD? Exit 1 when stale
│   ├── fetch_repository.py            # Fetch a public GitHub repo to a temp dir (stdlib)
│   ├── save_corrections.py            # Record a Phase 4 decision (id shape is validated)
│   ├── apply_corrections.py           # Re-apply corrections.json into the graph on every rebuild
│   ├── detect_stack_generic.py        # Route/model/auth packs for Go, Ruby, PHP, Java, C#, Rust, Kotlin, Elixir
│   ├── score_report.py                # Weighted scoring of a session against the 6-category rubric weights
│   ├── validate_mermaid.py            # Structural validator for .mmd diagram files
│   ├── generate_challenge.py          # Create a challenge manifest + starter files (Python, JS, JSX, TS, TSX)
│   ├── prepare_workspace.py           # Copy allowed starter files into an isolated workspace/
│   ├── run_checks.py                  # Run manifest checks in the workspace (security allow-list + 30s timeout)
│   ├── save_progress.py               # Create/update/load/list assessment session files
│   ├── generate_question_bank.py      # Generate a 4-category question bank from the graph (JSON + MD)
│   ├── assess.py                      # Orchestrate assessment sessions (start / answer / finish)
│   ├── plan_review.py                 # Spaced-retrieval planner: which questions to re-answer today
│   └── check_docs.py                  # Documentation lint: frontmatter, links, dead wiring, rubric ids
├── templates/
│   ├── project-graph.schema.json      # JSON Schema for the project graph
│   ├── rubric.schema.json             # JSON Schema for rubric files (incl. category fallback + hints)
│   ├── challenge.schema.json          # JSON Schema for challenge manifests
│   ├── assessment-result.schema.json  # JSON Schema for session files
│   ├── architecture-document.md       # Template for docs/architecture-overview.md
│   ├── data-flow-document.md          # Template for docs/data-flow.md
│   ├── core-logic-document.md         # Template for docs/core-logic.md
│   └── glossary-document.md           # Template for docs/glossary.md
├── rubrics/                           # Machine-readable scoring rubrics (validated against rubric.schema.json)
│   ├── explanation-auth-v1.json       # Question-specific (login/auth/JWT only)
│   ├── failure-scenario-db-v1.json    # Question-specific (database failure only)
│   ├── trade-off-stack-v1.json        # Question-specific (stack choice only)
│   ├── explanation-generic-v1.json    # Category fallback: every explanation question
│   ├── failure-generic-v1.json        # Category fallback: every failure question
│   ├── tradeoff-generic-v1.json       # Category fallback: every trade-off question
│   └── coding-generic-v1.json         # Category fallback: every coding question
├── tests/
│   ├── test_skill.py                  # Core detector/validator/build tests
│   ├── test_scoring.py                # score_report.py tests
│   ├── test_challenge_gen.py          # generate_challenge.py tests
│   ├── test_workspace.py              # prepare_workspace.py + run_checks.py tests
│   ├── test_assess.py                 # generate_question_bank.py + assess.py tests
│   ├── test_progress.py               # save_progress.py tests
│   ├── test_review_docs.py            # plan_review.py + check_docs.py + rubric selection tests
│   └── test_robustness.py             # Regression suite: dependency dirs, ignore rules, JS challenges, rubric coverage, freshness
├── examples/                          # Worked-example projects for detector testing
│   ├── README.md
│   ├── example-todo-app/              # React + Express + MongoDB (full detection)
│   ├── example-django-blog/           # Django + DRF + Postgres (partial)
│   ├── example-fastapi-tasks/         # FastAPI + SQLAlchemy + SQLite (partial)
│   └── example-nextjs-todo/           # Next.js 14 + Supabase (partial)
├── .github/
│   └── workflows/
│       └── test.yml                   # CI: runs tests + smoke on all 4 examples
├── .gitignore
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
└── LICENSE
```

Run the full suite with `python -m unittest discover -s tests -p "test_*.py"` (129 tests). CI runs it on
Python 3.8, 3.10 and 3.12 on ubuntu, plus 3.12 on windows, then smoke-tests all four example projects.

---

## How the Verification Loop Works (Key Differentiator)

After analysis, the agent shows you **three lists**:

1. **Verified from code** — facts with file:line citations
2. **Uncertain points** — specific questions (e.g., "hash algorithm not visible")
3. **Conflicts** — README says X, code shows Y

You respond **confirm / correct / don't know** for each. The graph updates:
- confirmed → `code-verified`
- corrected → `user-provided` (your note becomes evidence)
- don't know → stays `UNVERIFIED` (flagged in final report)

**No documentation is generated until you say "looks good."**

---

## Keeping the Analysis Honest

### What the graph knows about structure

`project-graph.json` carries `relationships`: file-level edges of three kinds —
`imports` (who pulls code from whom, resolved from `import`/`require`/`from …
import`), `tested_by` (test file matched to source by naming convention) and
`protects` (middleware guarding a route prefix).

These edges are what turn "what breaks if I delete this module?" into a
factual answer: the importers are listed, with evidence, instead of guessed.

### Exclusion rules

Dependency, build, cache and VCS directories (`node_modules`, `dist`, `build`, `.git`,
`venv`, `target`, `.next`, `coverage`, ...) are always skipped by **both**
the scanner and the detector. Third-party `package.json` files therefore never
shape your detected stack, and vendored code never leaks into env-var or
entry-point detection.

For anything else, drop a `.project-defenseignore` at the repository root. It
accepts the useful subset of gitignore syntax:

```gitignore
# generated code
*.generated.ts
vendor/

# keep this one even though the rule above matches it
!vendor/our-shim.js
```

### Graph freshness

`build_graph.py` stamps the graph with `analyzed_at` and `git_head`. Before any
phase quotes the graph, verify it still matches the checkout:

Every claim in the graph is old unless the source files still match it. `build_graph.py` records
the git HEAD **and** a content fingerprint, so freshness works even in a repo with no git history:

```bash
python scripts/check_graph_freshness.py .
# exit 0 = fresh, exit 1 = stale (prints commits_behind), exit 2 = no graph
# "checked_by": "git" | "content_fingerprint"
```

A stale graph is not a build failure — it is a signal that Phase 4's evidence
needs re-reading, and that the documents may describe last week's code.

### Scoring coverage

Every generated question is gradeable. A question-specific rubric only applies
when its `topic` keywords appear in the question text; otherwise the category
fallback rubric is used (`*-generic-v1`). Two consequences you can rely on:

- An answer with **no rubric is never counted as zero** — it is listed under
  `categories.<name>.unscored` so the readiness report can say how much of the
  session was actually graded.
- Scores produced by `assess.py`'s keyword fallback are tagged
  `scored_by: heuristic` and counted in `heuristic_scored`. The authoritative
  score is the agent's, reading `scoring_levels` in the rubric.

---

## The Study Loop (why it is not just a question bank)

Answering a question once tests **fluency**: the answer feels known today and is
gone in a week. An interview needs **storage strength**. The skill therefore
schedules retrieval instead of letting you re-read notes:

```bash
python scripts/plan_review.py .            # what to re-answer today
python scripts/plan_review.py . --write    # ...and save it as review-plan.md
```

- Every answered question moves along a Leitner ladder (1, 3, 7, 16, 35 days).
- A question whose mean concept score is below 2/3 is pulled **back** to the
  shorter interval instead of being pushed out.
- Questions you never answered are due immediately.
- The list is **interleaved** across categories, because mixed practice forces
  recall while blocked practice only forces pattern-matching.
- The plan is deterministic: same sessions plus same `--today` gives the same
  order, so you can test and audit it.

Each pass ends the same way: score the answer honestly against the rubric, then
let the ladder decide when it comes back.

---

## Example Learning Path Output (React + Express + MongoDB)

| Stage | Topic | Project Connection | Practice Task |
|-------|-------|-------------------|---------------|
| 1 | JS Fundamentals | Variables, functions in components | Refactor to arrow functions |
| 2 | React Basics | Components in `src/components/` | Build a Button with props |
| 3 | Forms/Validation | Login form in `src/pages/Auth.tsx` | Recreate login form |
| 4 | HTTP/API | Axios in `src/api/client.ts` | Write fetch wrapper |
| 5 | Node/Express | Routes in `server/routes/*.js` | Add a new route |
| 6 | MongoDB | Models in `server/models/*.js` | Write User query |
| 7 | Auth | JWT in `server/middleware/auth.js` | Implement JWT verify |
| 8 | Error Handling | Error boundaries, API errors | Add try/catch to route |
| 9 | Testing | (your test setup) | Test `/api/login` |
| 10 | **Rebuild Challenge** | `server/middleware/auth.js` | Recreate from scratch |

---

## Example Question Bank Entry

```markdown
### Q: What happens if the JWT expires mid-request?

**Why interviewers ask:** Tests understanding of token lifecycle, middleware, and UX.

**Expected concepts (rubric):**
- Middleware checks `exp` claim
- Returns 401 Unauthorized
- Frontend redirects to login
- Refresh token strategy (if implemented)

**Strong answer:** "The auth middleware decodes the JWT and checks the `exp` timestamp.
If expired, it returns 401 before hitting the route handler. The frontend's axios
interceptor catches 401, clears the access token, calls the refresh endpoint...
if that fails, redirects to /login."

**Weak answers:** "It crashes," "The user gets logged out" (no mechanism), "Not sure."

**Follow-up:** "How would you implement silent refresh without flicker?"

**Coding task:** Add a refresh-token endpoint and update the interceptor.
```

---

## Installation by Agent

Use `npx skills add` — it handles the right directory for every agent automatically. Users install directly from the published repo; no fork required.

```bash
# Pin the skill and target a specific agent (non-interactive, CI/CD-friendly)
npx -y skills add Hyperterror/Project-defense --skill project-defense-skill --agent claude-code
npx -y skills add Hyperterror/Project-defense --skill project-defense-skill --agent antigravity
npx -y skills add Hyperterror/Project-defense --skill project-defense-skill --agent codex
npx -y skills add Hyperterror/Project-defense --skill project-defense-skill --agent cursor
npx -y skills add Hyperterror/Project-defense --skill project-defense-skill --agent opencode

# All detected agents at once
npx skills add Hyperterror/Project-defense --all
```

`Hyperterror/Project-defense` is the `owner/repo` on GitHub. `--skill project-defense-skill` matches the `name` field in this repo's
`SKILL.md` frontmatter and selects it explicitly (handy if a repo ever ships
more than one skill).

The CLI supports 30+ agents and lets you choose between a **symlink** (single
source of truth, easy updates) or a **copy** (useful when symlinks aren't
supported). Agent-directory mappings are maintained in the skills CLI itself,
so they stay correct as agents evolve — you don't have to update this repo to
track them.

**Updating later:**
```bash
npx skills check      # see if a newer version is available
npx skills update     # pull the latest
```

**Removing:**
```bash
npx skills remove project-defense-skill
```

### Kiro

Kiro uses steering files instead of `SKILL.md`. The `npx skills add` flow
will install the files, but you need one extra step: copy the `instructions/`
folder contents into `.kiro/steering/` and reference them from a top-level
steering file so Kiro loads the workflow context automatically.

The Python scripts work without any agent config — run them directly:
```bash
python3 /path/to/skill/scripts/scan_repository.py .
```
Then ask Kiro to continue from the scan output.

---

## Scope

What this skill is, what it is deliberately not, and the bar a change has to
clear: see [SCOPE.md](SCOPE.md).

---

## Roadmap (v1 → Platform)

- [x] Foundation: SKILL.md, verification loop, React/Express/MongoDB
- [x] Documentation + Mermaid diagrams
- [x] Learning path + question bank + mock interview + readiness report
- [x] Machine-readable rubrics + weighted scoring (score_report.py)
- [x] Practice Mode (challenges, isolated workspace, progressive hints, manifest checks)
- [x] Assessment Mode (session tracking, strict/guided modes, question bank, scoring)
- [ ] Second stack (Next.js/Supabase)
- [ ] Example projects + sample outputs
- [ ] Public release + feedback collection
- **Phase 2 (later):** Web platform — saved progress, GitHub OAuth, private repos,
  no-AI timed sandbox, live-assessment simulation

---

## License

MIT — see [LICENSE](LICENSE).