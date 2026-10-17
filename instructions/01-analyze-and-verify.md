# Analyze and Verify — Phases 1-4 Checklist

This is the step-by-step checklist agents follow for repository analysis and
user verification. The full rationale for each phase is in `00-workflow.md`.

---

## Phase 1: Repository Ingestion

**Determine the input: local path or GitHub URL.**

- If the user gave a **GitHub URL** (`https://github.com/<owner>/<repo>`), run
  `python3 scripts/fetch_repository.py <url>` first. It downloads a tarball
  from `api.github.com` to a temp dir and prints the local path on stdout.
  Capture that path -- it becomes `<repo-root>` for the rest of the workflow.
  The temp dir is auto-cleaned on exit. Public repos only in v1; private
  repos return an error and the agent should tell the user.
- If the user gave a **local path**, use it directly as `<repo-root>`.

**Then run `scripts/scan_repository.py <repo-root>`** on the project you want to
analyze (NOT on the skill folder itself). It outputs
`.project-defense/scan-facts.json` with:
- repo_root, folder_structure, languages, dependency_manifests
- readme_path, test_dirs, test_frameworks, config_files
- entry_points, env_vars, run_commands

**If the script fails or misses things:**
- Read package.json / requirements.txt / pyproject.toml manually.
- Search for entry points: `search_files(pattern="^(index|main|app|server)\.(js|ts|py)$", target="files")`.
- Find config: `search_files(pattern="\.(env|yaml|yml|toml|ini|conf)$", target="files")`.
- List test dirs: `search_files(pattern="test|spec|__tests__", target="files")`.

**Record every fact with file path.** No guessing.

---

## Phase 2: Static Analysis

**Run `scripts/detect_code_facts.py <repo-root>`.** It performs stack-specific
code extraction (Express routes, React components, Mongoose models, API calls,
auth signals) and writes `.project-defense/code-facts.json` with structured
entries — every entry already has `evidence: { file, lines, excerpt, status }`.

You can then merge this into scan-facts.json by reading both files.

**For React + Express + MongoDB (v1 supported stack), verify these specifically:**

| What to find | Where to look | Evidence format |
|---|---|---|
| React components | `src/components/`, `src/pages/` | file, lines, export name |
| React hooks/context | `src/hooks/`, `src/context/` | file, lines, hook name |
| Express routes | `server/routes/`, `server/app.js` | method, path, handler file:line |
| Middleware | `server/middleware/` | file, lines, exported fn |
| Mongoose models | `server/models/` | model name, schema fields |
| API calls from frontend | `src/api/`, `src/services/` | endpoint, method, calling file |
| Auth: JWT handling | `server/middleware/auth.js`, `server/utils/token.js` | file, lines, algorithm |
| Password hashing | `server/controllers/auth.js`, `server/models/User.js` | file, lines, bcrypt/scrypt |
| Protected routes | route files using auth middleware | file, lines, middleware name |
| Env vars used | `process.env.*`, `os.getenv()` | var name, file, line |

**For anything not covered:** read the code directly and cite it.

**If the repo was fetched from a URL:** the temp dir is auto-cleaned. To
preserve artifacts, re-run with `scripts/fetch_repository.py <url> --keep <dir>`
to keep the extracted code, OR copy `.project-defense/` out of the temp dir
into a persistent location the user specifies before exit.

**Output:** all findings go into the project graph (Phase 3) with status
"code-verified".

---

## Phase 3: Build Project Graph

**Create `.project-defense/project-graph.json` matching
`templates/project-graph.schema.json`** by running
`scripts/build_graph.py <repo-root>`. The script reads both
`scan-facts.json` and `code-facts.json` and emits a graph that
auto-validates against the schema. Then refine the empty sections
(pages, controllers, services, user_flows, data_flows) by reading the code
yourself.

**Required top-level keys:**
- project: { name, purpose, stack[], entry_points[] }
- frontend: { pages[], components[], state_management[], api_calls[] }
- backend: { routes[], middleware[], controllers[], services[] }
- data: { models[], relationships[], migrations[] }
- auth: { strategy, token_handling, protected_routes[] }
- user_flows[]
- data_flows[]
- risks[]
- uncertainties[]

**Every array entry MUST have:**
```json
{
  "name": "...",
  "details": { ... },
  "evidence": { "file": "path/to/file.ext", "lines": [10, 25], "excerpt": "code...", "status": "code-verified" }
}
```

**Status values:** "code-verified" | "user-provided" | "UNVERIFIED"

**Validate:** `python3 scripts/validate_graph.py .project-defense/project-graph.json templates/project-graph.schema.json`
(must exit 0). Fix any reported `path: reason` errors before moving to Phase 4.

---

## Phase 4: Verification Loop

**Present the understanding report in three sections:**

### A. Verified from Code
List each graph entry with status "code-verified":
- Name / type
- Key details
- File:lines
- Code excerpt (2-3 lines)

### B. Uncertain Points
List each "UNVERIFIED" entry as a specific question:
- "File X line Y calls `hash()` but doesn't show the algorithm -- is it bcrypt?"
- "Route POST /api/users exists but no validation middleware visible -- where is input validated?"

### C. Conflicts
- "README says 'uses PostgreSQL' but only MongoDB/Mongoose code found."
- "README claims 'full test coverage' but only 2 test files exist."

**For each item, ask the user:** "Confirm? Correct? Don't know?"

**Update the graph:**
- Confirm → keep "code-verified"
- Correct → change to "user-provided", add user's note to evidence
- Don't know → keep "UNVERIFIED"

**Repeat until user says "looks good" or equivalent.**

**CORE RULE:** Do NOT proceed to Phase 5 until the user has explicitly
confirmed the understanding report.

---

## Checklist Summary (tick each before moving on)

- [ ] scan-facts.json exists and is complete
- [ ] All stack-specific detectors run (React, Express, MongoDB, Auth)
- [ ] project-graph.json validates against schema
- [ ] Every graph entry has evidence with file, lines, excerpt, status
- [ ] Verification report presented in 3 sections (Verified, Uncertain, Conflicts)
- [ ] User has confirmed/corrected every item
- [ ] Updated project-graph.json saved with resolved statuses