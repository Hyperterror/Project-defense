# Example Projects

These four small projects are used to dry-run the project-defense-skill
workflow. They are not runnable applications — they exist to exercise
the detectors and to serve as fixtures for the §15 validation plan.

| Project | Stack | Detector coverage | Use it to test |
|---|---|---|---|
| [example-todo-app](./example-todo-app/) | React + Express + MongoDB | **Full** | End-to-end workflow: scan + detect + build + verify |
| [example-django-blog](./example-django-blog/) | Django + DRF + PostgreSQL | **Full** for routes, auth, models | URLconf `include()` chaining, DRF router + permission classes |
| [example-fastapi-tasks](./example-fastapi-tasks/) | FastAPI + SQLAlchemy + SQLite | **Full** for routes, auth, models | Decorator routes, `Depends()` guards, jose JWT |
| [example-nextjs-todo](./example-nextjs-todo/) | Next.js 14 + Supabase | **Full** for routes, auth, components | File-based routes (`app/api/**/route.ts`), delegated cookie auth |

Each example produces routes, an auth strategy and models from code alone, so
the generated question bank is project-specific in all four:

| Project | Routes | Protected routes | Questions |
|---|---|---|---|
| example-todo-app | 7 | 4 | 18 |
| example-django-blog | 15 | 12 | 12 |
| example-fastapi-tasks | 7 | 4 | 11 |
| example-nextjs-todo | 4 | 0 | 9 |

Counts are from `scripts/generate_question_bank.py` at the current detectors. The
Django project asks more because its stack names three technologies
(`Django REST Framework`, `Django`, `PostgreSQL`) and a stack-pair trade-off and a
database trade-off question are both generated; the todo app's Mongoose stack is
one entry, so it gets the database question instead.

## What "full" vs "partial" means

**Full coverage** means the detectors auto-find the right facts:

- All routes
- All components / hooks
- All models with schema
- Auth strategy
- Protected routes
- Risk flags (e.g., no tests)

**Partial coverage** (what remains true for every stack) means the agent must
read code manually to fill gaps — chiefly the service/controller layer, user
flows and data flows. The skill's instructions
(instructions/01-analyze-and-verify.md, Phase 3) tell the agent to do exactly
this, and to mark what it could not verify.

## Running the workflow on each

```bash
# Replace <example> with one of: example-todo-app, example-django-blog,
# example-fastapi-tasks, example-nextjs-todo
python3 scripts/scan_repository.py examples/<example>
python3 scripts/detect_code_facts.py examples/<example>
python3 scripts/build_graph.py examples/<example>
python3 scripts/validate_graph.py examples/<example>/.project-defense/project-graph.json
```

The example-todo-app builds a complete, schema-valid graph. The other
three build partial graphs with empty sections (controllers, services,
etc.) that the agent refines during the verification loop.

## Adding a new example

See `../CONTRIBUTING.md` for the contribution guidelines. The short
version:

1. Pick a stack not yet covered
2. Make a small (under 500 lines) project that exercises the detectors
3. Include a `.project-defense/` showing expected output
4. Document in the example's README what gets detected and what doesn't
5. Add a row to the table above
