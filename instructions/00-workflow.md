# Project Defense Skill -- Master Workflow Reference

This document defines all 10 phases of the project-defense workflow in full
detail. The operational checklists agents follow step by step live in
`01-analyze-and-verify.md` (phases 1-4) and `02-generate-docs.md` (phases 5-10).
Refer here for the rationale and rules behind each phase.

---

## Phase 1: Repository Ingestion

**Goal:** determine what the project is and what it contains before reading any
source code in depth.

**Inputs:** the repository root path.

**Steps:**
1. Record the absolute path of the repository root.
2. List the top-level folder structure (depth 2).
3. Detect languages by file extension counts.
4. Find dependency manifests: package.json, requirements.txt, pyproject.toml, Cargo.toml, go.mod, pom.xml, build.gradle, etc.
5. Locate README, LICENSE, and any docs/ folder.
6. Identify test directories and test frameworks.
7. Find configuration files (.env.example, docker-compose.yml, .github/workflows/, etc.).
8. Identify entry point candidates: index.js, main.py, app.py, server.js, src/main.tsx, etc.
9. Record required environment variables from .env.example or documentation.
10. Extract build and run commands from package.json scripts, Makefile, README, or docker files.

**Output:** a JSON object written to `.project-defense/scan-facts.json` with keys:
- repo_root, folder_structure, languages, dependency_manifests, readme_path,
  test_dirs, test_frameworks, config_files, entry_points, env_vars, run_commands.

**Evidence rule:** every detected fact must cite the file path it came from.

---

## Phase 2: Static Analysis

**Goal:** extract structured facts from code using deterministic scripts where
possible, so the agent does not have to guess.

**Inputs:** the scan-facts.json from Phase 1, plus the source files it points to.

**Steps:**
1. Run `scripts/scan_repository.py` on the repo root. It parses dependency
   manifests, detects frameworks, extracts routes, components, models, API calls,
   environment variables, and test files.
2. For anything the script cannot cover (custom patterns, business logic), the
   agent reads the relevant source files directly and cites them.
3. All extracted facts are recorded with: item type, key details, file path,
   line numbers, code excerpt (max 120 chars), and status = "code-verified".

**Output:** enriched facts merged into the project graph (Phase 3). The raw
script output is also preserved in `.project-defense/scan-facts.json`.

**Stack-specific detectors (v1):**
- React: components, hooks, context providers, pages/routes.
- Express: routes, middleware, controllers, error handlers.
- MongoDB/Mongoose: models, schemas, indexes, virtuals.
- Authentication: JWT handling, password hashing, protected routes.

**Evidence rule:** if a detector cannot confirm something, do not invent it --
mark it UNVERIFIED and move to Phase 4.

---

## Phase 3: Project Graph

**Goal:** assemble all verified facts into a single machine-readable JSON
document that conforms to `templates/project-graph.schema.json`.

**Structure:**
```json
{
  "project": { "name": "", "purpose": "", "stack": [], "entry_points": [] },
  "frontend": { "pages": [], "components": [], "state_management": [], "api_calls": [] },
  "backend": { "routes": [], "middleware": [], "controllers": [], "services": [] },
  "data": { "models": [], "relationships": [], "migrations": [] },
  "auth": { "strategy": "", "token_handling": "", "protected_routes": [] },
  "user_flows": [],
  "data_flows": [],
  "risks": [],
  "uncertainties": []
}
```

**Rules:**
- Every array entry must include `evidence`: { file, lines, excerpt, status }.
- Status is one of: "code-verified", "user-provided", "UNVERIFIED".
- No free-text descriptions without evidence.
- The graph is the single source of truth for all downstream phases.

**Output:** `.project-defense/project-graph.json` (validated against the schema).

---

## Phase 4: Verification Loop

**Goal:** the user confirms, corrects, or adds to the agent's understanding
BEFORE any final documentation is generated. This is the main differentiator.

**Steps:**
1. Present the understanding report in three parts:
   - **Verified from code:** list each graph entry with status "code-verified",
     showing file path and excerpt.
   - **Uncertain points:** list each "UNVERIFIED" entry with the specific
     question (e.g., "Is password hashing done with bcrypt? File X line Y shows
     a hash call but the algorithm is not clear.").
   - **Conflicts:** where README claims something the code does not support.
2. For each item, the user responds: confirm, correct, or "I don't know".
3. Update the project graph:
   - Confirmed "code-verified" stays "code-verified".
   - User corrections become "user-provided" with the user's note as evidence.
   - "I don't know" stays "UNVERIFIED" and is flagged in the readiness report.
4. Repeat until the user says "looks good" or equivalent.

**Core rule (from SKILL.md):** Do not generate final documentation until the
user has reviewed and confirmed the project-understanding report.

**Output:** updated `.project-defense/project-graph.json` with resolved
statuses.

---

## Phase 5: Documentation Generation

**Goal:** produce three standalone documents from the VERIFIED project graph.

**Documents (each in `.project-defense/docs/`):**
1. `architecture-overview.md` -- system overview, technology stack, main
   components, component interactions, key design decisions (verified only),
   interview-ready summary, evidence appendix.
2. `data-flow.md` -- request lifecycle, data movement between layers (frontend
   -> API -> DB -> response), state transitions, async flows, evidence appendix.
3. `core-logic.md` -- the project's core algorithms and business rules,
   step-by-step explanations, edge cases handled, evidence appendix.

**Template:** each document follows `templates/architecture-document.md`
structure (purpose, stack, components, lifecycle/steps, decisions, summary,
evidence).

**Rule:** only "code-verified" and "user-provided" entries appear in the main
body. "UNVERIFIED" entries appear only in the evidence appendix with a warning.

---

## Phase 6: Diagram Generation

**Goal:** emit Mermaid diagram source files (text, not images) from the verified
project graph.

**Diagrams (in `.project-defense/diagrams/`):**
1. `architecture.mmd` -- component diagram: frontend, backend, database,
   external services, message queues. Nodes = components; edges = calls/data flow.
2. `data-flow.mmd` -- sequence or flow diagram: user action -> frontend ->
   API -> DB -> response. Shows data transformations at each step.
3. `user-flow.mmd` -- flowchart of primary user journeys (login, core feature,
   error recovery).

**Generation:** agent writes Mermaid syntax directly from graph entries. No
external tools required. Diagrams render in GitHub, GitLab, Notion, Obsidian,
and most Markdown viewers.

---

## Phase 7: Learning Path

**Goal:** build a personalized curriculum from the user's actual project gaps.

**Method:**
1. Scan the project graph for detected features (JWT auth, React forms,
   Express middleware, MongoDB models, testing, error handling, etc.).
2. Map each feature to a learning stage (fundamentals -> project-level).
3. Produce a table: Stage, Topic, Project Connection, Practice Task.
4. Include a "Rebuild Challenge" as the final stage: recreate a core feature
   without copying code.

**Output:** `.project-defense/learning-path.md`.

**Example (React + Express + MongoDB):**
| Stage | Topic | Project Connection |
|---|---|---|
| 1 | JS fundamentals | Variables, functions, arrays used in components |
| 2 | React basics | Components, props, state in src/components/ |
| 3 | Forms/validation | Login/register forms in src/pages/Auth.tsx |
| 4 | HTTP/API | Axios calls in src/api/client.ts |
| 5 | Node/Express | Routes in server/routes/*.js |
| 6 | MongoDB | Models in server/models/*.js |
| 7 | Auth | JWT in server/middleware/auth.js |
| 8 | Error handling | Error boundaries, API error responses |
| 9 | Testing | Write a test for /api/login |
| 10 | Rebuild challenge | Recreate the auth middleware from scratch |

---

## Phase 8: Question Bank

**Goal:** generate project-specific interview questions with rubrics.

**Four categories, drawn from the project graph:**
1. **Explanation:** "Walk me through what happens when a user submits the
   login form." "Explain the architecture."
2. **Failure scenarios:** "What happens if MongoDB is down?" "What if the JWT
   secret is rotated?" "What if an env var is missing at startup?"
3. **Trade-offs:** "Why MongoDB over PostgreSQL?" "Why Express over Fastify?"
   "How would this scale to 10x traffic?"
4. **Coding tasks:** "Add validation to the registration endpoint." "Write a
   test for the expired-token case." "Fix this broken auth middleware."

**Each question includes:**
- The question text.
- Why interviewers ask it.
- Expected concepts (the rubric).
- Strong sample answer.
- Common weak answers.
- Follow-up question.
- Coding task (where relevant).

**Output:** `.project-defense/question-bank.md`.

---

## Phase 9: Mock Interview

**Goal:** run a structured, timed interview scored against rubrics -- not open
chat.

**Structure (7 segments, ~45-60 min total):**
1. Project overview (2 min) -- user summarizes the project.
2. Architecture (8 min) -- components, data flow, design decisions.
3. Deep dive: one critical flow (10 min) -- e.g., authentication, payment,
   real-time feature.
4. Failure scenarios (8 min) -- 3-4 "what if" questions from the question bank.
5. Trade-offs (7 min) -- 2-3 architectural decisions.
6. Coding challenge (10 min) -- one task from the question bank, user writes
   code in the repo (or pseudocode). Agent evaluates against rubric.
7. Reflection (5 min) -- "What would you improve? What technical debt exists?"

**Scoring:** each segment scored 0-3 per rubric concept (0=missing,
1=partial, 2=correct, 3=thorough). Segment weights: deep dive 25%, coding 25%,
architecture 20%, failures 15%, trade-offs 10%, overview 5%, reflection 10%.

**Rubric-driven scoring (machine-readable):**
The agent loads rubric files from the `rubrics/` directory that match the
question being asked. Matching is done by `rubric_id` — each question in the
question bank carries a `rubric_id` that points to a file in `rubrics/`
(e.g. `rubrics/explanation-auth-v1.json`).

For each rubric concept, the agent scores the user's answer 0-3 using the
`scoring_levels` descriptions in the rubric file:
- 0 = missing (description in rubric `scoring_levels.<concept>["0"]`)
- 1 = partial (description in rubric `scoring_levels.<concept>["1"]`)
- 2 = correct (description in rubric `scoring_levels.<concept>["2"]`)
- 3 = thorough (description in rubric `scoring_levels.<concept>["3"]`)

**Recording Q&A exchanges:**
After each answer, the agent writes the Q&A pair to the session JSON file at
`.project-defense/sessions/<session-id>.json` via `save_progress.py update`:
```json
{
  "question_id": "q-e001",
  "question_text": "Walk me through the login flow.",
  "answer_text": "The user submits the form...",
  "rubric_id": "explanation-auth-v1",
  "timestamp": "2024-01-01T00:00:00+00:00"
}
```

**On interview completion:**
The agent calls `score_report.py` (or `assess.py finish <session-id>`) on the
session file to produce the final score. The score JSON written to
`.project-defense/sessions/<session-id>-score.json` is the authoritative
output. It contains `overall_score` (0.0-1.0), per-category `categories`
breakdown, `strengths`, and `gaps`.

**Populating the readiness report:**
The agent uses the resulting score JSON to populate the Phase 10 readiness
report — pulling `overall_score`, `strengths`, `gaps`, and per-category
`categories` directly from the score file rather than recomputing them.

**Output:** scores recorded in `.project-defense/readiness-report.md` (Phase 10).

---

## Phase 10: Readiness Report

**Goal:** give the user a concrete verdict with prioritized next steps.

**Contents of `.project-defense/readiness-report.md`:**
1. Overall readiness score (0-100, weighted from Phase 9).
2. Strengths (top 3 scored areas).
3. Critical gaps (areas scoring below 1.5/3, with file references).
4. Recommended next steps (priority ordered, each linked to a file/phase).
5. "UNVERIFIED" items from the project graph that need human clarification.
6. Rebuild challenge result (if attempted).

**Rule:** the report must be actionable -- "study React hooks" is weak;
"review useEffect cleanup in src/components/DataFetcher.tsx lines 23-31" is
strong.