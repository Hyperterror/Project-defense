# Example FastAPI Tasks

A small FastAPI + SQLAlchemy + SQLite tasks app. **Experimental stack** —
exercises the skill's Python backend detector. FastAPI routes (`@app.get`,
`@app.post`, etc.) are NOT auto-detected yet; the agent must read
`app/main.py` and add them to the graph manually in Phase 4.

## Try the skill on this

```bash
python3 scripts/scan_repository.py examples/example-fastapi-tasks
python3 scripts/detect_code_facts.py examples/example-fastapi-tasks
python3 scripts/build_graph.py examples/example-fastapi-tasks
```

The detector should find:
- 2 SQLAlchemy models (`User`, `Task`) via the Python ORM detector
- JWT decode in `get_current_user` and `create_access_token`
- bcrypt via passlib's `CryptContext(schemes=["bcrypt"])`
- 2 env vars (DATABASE_URL, JWT_SECRET)

## What's missing (manual work in Phase 4)

FastAPI's `@app.get`, `@app.post`, etc. route decorators are not in the
JS/TS detector. The agent should grep for them in the Python source
during Phase 4 and add to the graph.

## Not a runnable app

Like the other examples, this omits Alembic migrations, tests, and a
real database. Use it as a detector fixture.
