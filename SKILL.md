---
name: project-defense-skill
description: Analyze a local repo and prepare the user to defend it in an interview.
---

# Project Defense Skill

This skill turns the agent into a project-defense coach: it analyzes the user's own repository and verifies its understanding of the project's purpose with the user before producing anything. The deliverables are architecture and data-flow documentation with Mermaid diagrams, a personalized learning path, a project-specific question bank, and a structured mock interview scored against rubrics. It is not a generic code explainer, and it is not a linter.

## When to Use
- The user says 'understand my project' or similar.
- 'audit this repository' or 'audit this repo' (works with a local path or a GitHub URL)
- 'prepare me to explain this project in an interview'
- 'find gaps in my understanding of this codebase'
- 'help me rebuild a core feature without AI assistance'
- 'run a mock technical interview on my project'

## When NOT to Use
- One-off 'explain this function' requests — just answer directly.
- Linting or formatting.
- Performance profiling.
- Full code review of a PR.

## Core Rule
**Do not generate final documentation until the user has reviewed and confirmed the project-understanding report (see instructions/01-analyze-and-verify.md, Phase 4).**

## Evidence Rules
- Every major claim must cite file path, line number, and a short code excerpt.
- Every graph entry carries a status: code-verified, user-provided, or UNVERIFIED.
- Never invent routes, APIs, database fields or user flows.
- If README and code conflict, the code takes priority — but always flag the conflict.
- Ask the user before assuming intent, deployment or business rules.

## The Workflow
1. Repository ingestion — read the file tree, detect the stack, record baseline facts.
2. Static analysis — run scripts/scan_repository.py to extract routes, models, and structure.
3. Project graph — build the structured project graph in project-graph.json from scan results.
4. Verification loop — present the understanding report; the user confirms or corrects it.
5. Documentation — write docs/architecture-overview.md, docs/data-flow.md, docs/core-logic.md.
6. Diagrams — emit Mermaid sources: diagrams/architecture.mmd, data-flow.mmd, user-flow.mmd.
7. Learning path — build learning-path.md tailored to the gaps the user shows.
8. Question bank — generate project-specific questions into question-bank.md.
9. Mock interview — run a structured interview scored against rubrics.
10. Readiness report — produce readiness-report.md with gap analysis and next steps.

Phases 1-4 live in instructions/01-analyze-and-verify.md.
Phases 5-10 live in instructions/02-generate-docs.md.
Full phase mechanics for every phase live in instructions/00-workflow.md.

## Artifacts
All outputs go in a `.project-defense/` folder at the analyzed repository's root:

- `scan-facts.json` — raw output of `scripts/scan_repository.py`
- `code-facts.json` — raw output of `scripts/detect_code_facts.py` (routes, components, models, auth)
- `project-graph.json` — the project graph; schema: `templates/project-graph.schema.json`
- `docs/architecture-overview.md` — system overview, components, stack
- `docs/data-flow.md` — request lifecycle and data movement between layers
- `docs/core-logic.md` — the project's core algorithms and business rules
- `diagrams/architecture.mmd` — Mermaid architecture diagram source
- `diagrams/data-flow.mmd` — Mermaid data-flow diagram source
- `diagrams/user-flow.mmd` — Mermaid user-flow diagram source
- Mermaid files are text, not rendered images
- `learning-path.md` — personalized learning path
- `question-bank.md` — project-specific interview questions
- `readiness-report.md` — final readiness verdict

## Supported Stacks
Version 1 fully supports: **React + Node/Express + MongoDB**.
The other stacks are experimental — run the workflow, but tell the user coverage is partial:
- Next.js + Supabase/Firebase
- Python Flask/FastAPI + SQL
- Django + PostgreSQL
- React Native + Firebase

## Privacy & Safety
See [SECURITY.md](SECURITY.md) for the full privacy and safety contract.

Summary:
- Analyzes only the opened local folder (or a public GitHub repo the user explicitly names). No other code is touched.
- For GitHub URLs: the skill downloads a tarball from `api.github.com` to a temp dir, scans it, and deletes the temp dir. The repo must be public; private repos are not supported in v1.
- Scripts never phone home, never log source code, and never send repo contents anywhere except to `api.github.com` for the one tarball fetch.
- Avoid reading .env / credentials / private keys / token files unless explicitly asked.
- The skill never pushes code, deletes files outside `.project-defense/` and the temp fetch dir, or installs packages on its own.
- **Please review `scripts/*.py` before running them.** They are short and well-commented, but you should not run any code on your machine that you have not read.

## Prerequisites
- Python 3.8+ available for scripts/scan_repository.py (stdlib only, no pip installs needed).
- Everything else works with just file reading and search tools.
