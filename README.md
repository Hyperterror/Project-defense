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
5. **Generates 3 documents** — architecture overview, data flow, core logic
6. **Emits 3 Mermaid diagrams** — architecture, data flow, user flow (text, versionable)
7. **Creates a learning path** — 10 stages mapped to *your* project's actual features
8. **Builds a question bank** — explanation, failure scenarios, trade-offs, coding tasks, each linked to a machine-readable rubric
9. **Runs a mock interview** — 7 segments, scored against rubrics (0–3 per concept)
10. **Produces a readiness report** — score, strengths, gaps, prioritized next steps with file references

It also has two interactive coaching modes that build on the analyzed graph:

- **Practice Mode** — generates a coding challenge from your graph (function reconstruction, bug fix, or test writing), sets up an isolated workspace with starter files, coaches you with progressive hints, and runs manifest checks against your solution. Your original files are never modified.
- **Assessment Mode** — runs a structured assessment against the question bank, records every Q&A in a session file, scores each answer against its rubric, and produces a weighted overall score. Strict mode gives no hints; guided mode offers rubric hints when your score is low.

---

## Quick Start

The fastest way to install this skill into your AI coding agent is with the
[skills CLI](https://github.com/antfu/skills-cli) (the open agent-skills
package manager). It auto-detects your agent's skills directory and symlinks
the skill folder — no manual `cp` and **no fork required**. Users install
directly from the published repo.

```bash
# 1. Install the skill (interactively pick which agent(s) to target)
#    Replace <owner>/project-defense with the repo where this skill is published.
npx skills add <owner>/project-defense

#    Pin the exact skill by name (matches the `name` in SKILL.md frontmatter)
#    and target a specific agent, non-interactively:
npx -y skills add <owner>/project-defense --skill project-defense-skill --agent claude-code
npx -y skills add <owner>/project-defense --skill project-defense-skill --agent antigravity
npx -y skills add <owner>/project-defense --skill project-defense-skill --agent codex

#    Install to all detected agents at once:
npx skills add <owner>/project-defense --all

#    Install globally (available across all your projects) instead of per-project:
npx skills add <owner>/project-defense -g

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

`<owner>/project-defense` is the GitHub `owner/repo` where this skill is
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

## Supported Stacks (v1)

| Stack | Status |
|-------|--------|
| **React + Node/Express + MongoDB** | **Fully supported** — all detectors active |
| Next.js + Supabase/Firebase | Experimental |
| Python Flask/FastAPI + SQL | Experimental |
| Django + PostgreSQL | Experimental |
| React Native + Firebase | Experimental |

Experimental stacks: the workflow runs, but detector coverage is partial. The
agent will tell you which parts are UNVERIFIED.

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
│   └── core-logic.md
├── diagrams/
│   ├── architecture.mmd      # Mermaid source (renders in GitHub, Notion, Obsidian...)
│   ├── data-flow.mmd
│   └── user-flow.mmd
├── challenges/
│   └── <challenge-id>/
│       ├── manifest.json     # Challenge definition (validated against challenge.schema.json)
│       ├── starter/          # Starter files (TODO stubs / seeded bugs / test skeletons)
│       ├── workspace/        # Isolated copy of allowed files for you to edit
│       ├── workspace.json    # Workspace metadata
│       └── result.json       # check run results (PASSED/FAILED/NOT_RUN/INFRASTRUCTURE_ERROR)
├── sessions/
│   ├── <session-id>.json     # Assessment/interview session (Q&A, scores)
│   └── <session-id>-score.json  # Weighted score report
├── learning-path.md
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
│   ├── scan_repository.py             # Repo scanner (stdlib, Python 3.8+)
│   ├── detect_code_facts.py           # Stack-specific code detectors (routes, components, models...)
│   ├── build_graph.py                 # Merges scan + code-facts into schema-valid project-graph.json (+ session_identity)
│   ├── validate_graph.py              # JSON Schema validator for project-graph.json
│   ├── fetch_repository.py            # Fetch a public GitHub repo to a temp dir (stdlib)
│   ├── save_corrections.py            # Read/write .project-defense/corrections.json
│   ├── score_report.py                # Weighted scoring of a session against the 6-category rubric weights
│   ├── validate_mermaid.py            # Structural validator for .mmd diagram files
│   ├── generate_challenge.py           # Create a challenge manifest + starter files from the project graph
│   ├── prepare_workspace.py           # Copy allowed starter files into an isolated workspace/
│   ├── run_checks.py                  # Run manifest checks in the workspace (security allow-list + 30s timeout)
│   ├── save_progress.py               # Create/update/load/list assessment session files
│   ├── generate_question_bank.py      # Generate a 4-category question bank from the graph (JSON + MD)
│   └── assess.py                      # Orchestrate assessment sessions (start / answer / finish)
├── templates/
│   ├── project-graph.schema.json      # JSON Schema for the project graph
│   ├── rubric.schema.json             # JSON Schema for rubric files
│   ├── challenge.schema.json          # JSON Schema for challenge manifests
│   ├── assessment-result.schema.json  # JSON Schema for session files
│   ├── architecture-document.md       # Template for docs/architecture-overview.md
│   ├── data-flow-document.md          # Template for docs/data-flow.md
│   └── core-logic-document.md         # Template for docs/core-logic.md
├── rubrics/                           # Machine-readable scoring rubrics (validated against rubric.schema.json)
│   ├── explanation-auth-v1.json
│   ├── failure-scenario-db-v1.json
│   └── trade-off-stack-v1.json
├── tests/
│   ├── test_skill.py                  # Core detector/validator/build tests
│   ├── test_scoring.py                # score_report.py tests
│   ├── test_challenge_gen.py          # generate_challenge.py tests
│   ├── test_workspace.py              # prepare_workspace.py + run_checks.py tests
│   ├── test_assess.py                 # generate_question_bank.py + assess.py tests
│   └── test_progress.py               # save_progress.py tests
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

Run the full suite with `python3 -m unittest discover -s tests -p "test_*.py"` (67 tests).

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
npx -y skills add <owner>/project-defense --skill project-defense-skill --agent claude-code
npx -y skills add <owner>/project-defense --skill project-defense-skill --agent antigravity
npx -y skills add <owner>/project-defense --skill project-defense-skill --agent codex
npx -y skills add <owner>/project-defense --skill project-defense-skill --agent cursor
npx -y skills add <owner>/project-defense --skill project-defense-skill --agent opencode

# All detected agents at once
npx skills add <owner>/project-defense --all
```

`<owner>/project-defense` is the `owner/repo` where this skill is published on
GitHub. `--skill project-defense-skill` matches the `name` field in this repo's
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