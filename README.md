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
8. **Builds a question bank** — explanation, failure scenarios, trade-offs, coding tasks
9. **Runs a mock interview** — 7 segments, scored against rubrics
10. **Produces a readiness report** — score, strengths, gaps, prioritized next steps with file references

---

## Quick Start

```bash
# 1. Clone or copy this skill folder into your agent's skill directory
#    Examples:
#    ~/.claude/skills/project-defense-skill/          (Claude Code)
#    ~/.agents/skills/project-defense-skill/          (Codex CLI)
#    ~/.gemini/config/skills/project-defense-skill/   (Antigravity)
#    .kiro/steering/project-defense-skill/            (Kiro - see note below)

# 2. Open your project in the agent and invoke the skill
#    "Run the project-defense skill on this repository"
#    or explicitly: "$project-defense-skill" (Codex), "/project-defense-skill" (Claude)

# 3. The agent will:
#    - Run scripts/scan_repository.py
#    - Run scripts/detect_code_facts.py
#    - Build .project-defense/project-graph.json
#    - Present the verification report (Phase 4)
#    - After you confirm, generate all artifacts in .project-defense/
```

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

# 3. The agent will:
#    - Run scripts/scan_repository.py
#    - Build .project-defense/project-graph.json
#    - Present the verification report (Phase 4)
#    - After you confirm, generate all artifacts in .project-defense/
```

### Kiro Note
Kiro uses **steering files** (`.kiro/steering/`) rather than a SKILL.md format.
Copy the `instructions/` folder contents into `.kiro/steering/` and reference
them from a master steering file. The Python scanner still works — run it
manually: `python3 /path/to/skill/scripts/scan_repository.py .`

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
├── project-graph.json        # Validated against templates/project-graph.schema.json
├── docs/
│   ├── architecture-overview.md
│   ├── data-flow.md
│   └── core-logic.md
├── diagrams/
│   ├── architecture.mmd      # Mermaid source (renders in GitHub, Notion, Obsidian...)
│   ├── data-flow.mmd
│   └── user-flow.mmd
├── learning-path.md
├── question-bank.md
└── readiness-report.md
```

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
│   ├── build_graph.py                 # Merges scan + code-facts into schema-valid project-graph.json
│   ├── validate_graph.py              # JSON Schema validator for project-graph.json
│   └── fetch_repository.py            # Fetch a public GitHub repo to a temp dir (stdlib)
├── templates/
│   ├── project-graph.schema.json      # JSON Schema for the project graph
│   ├── architecture-document.md       # Template for docs/architecture-overview.md
│   ├── data-flow-document.md          # Template for docs/data-flow.md
│   └── core-logic-document.md         # Template for docs/core-logic.md
├── tests/
│   └── test_skill.py                  # 25 unit tests (run: python3 tests/test_skill.py)
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

| Agent | Skill Directory | Invoke |
|-------|-----------------|--------|
| Claude Code | `~/.claude/skills/project-defense-skill/` | "Run project-defense skill" |
| Codex CLI | `~/.agents/skills/project-defense-skill/` | `$project-defense-skill` |
| Antigravity | `~/.gemini/config/skills/project-defense-skill/` | Via Customizations → Skills |
| Kiro | `.kiro/steering/` (copy instructions/) | Reference in steering file |
| Cursor | `.cursor/skills/project-defense-skill/` | `@project-defense-skill` |

**One-liner to install (adjust target dir):**
```bash
cp -r /path/to/this/skill ~/.agents/skills/project-defense-skill
# or for Codex's new location:
cp -r /path/to/this/skill ~/.codex/skills/project-defense-skill
```

Then restart your agent session so it discovers the skill.

---

## Roadmap (v1 → Platform)

- [x] Foundation: SKILL.md, verification loop, React/Express/MongoDB
- [x] Documentation + Mermaid diagrams
- [x] Learning path + question bank + mock interview + readiness report
- [ ] Second stack (Next.js/Supabase)
- [ ] Example projects + sample outputs
- [ ] Public release + feedback collection
- **Phase 2 (later):** Web platform — saved progress, GitHub OAuth, private repos,
  no-AI timed sandbox, live-assessment simulation

---

## License

MIT — see [LICENSE](LICENSE).