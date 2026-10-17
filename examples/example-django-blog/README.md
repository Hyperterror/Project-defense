# Example Django Blog

A small Django + DRF + PostgreSQL blog. **Experimental stack** — exercises
the skill's Python backend detector, but the Django-specific routes (URL
patterns, DRF ViewSets) are not yet auto-detected. The skill will still
find: Django models, JWT auth, bcrypt, and the env vars.

## Try the skill on this

```bash
python3 scripts/scan_repository.py examples/example-django-blog
python3 scripts/detect_code_facts.py examples/example-django-blog
python3 scripts/build_graph.py examples/example-django-blog
```

The detector should find:
- 2 Django models (`Post`, `Comment`) via the Python ORM detector
- JWT verify in `blog/auth.py` and `blog/middleware.py`
- bcrypt (via `password` field handling in `register`)
- 6+ env vars (DJANGO_SECRET_KEY, POSTGRES_*, etc.)

## What's missing (manual work in Phase 4)

Django routes (URL patterns in `urls.py` and `auth_urls.py`) are NOT
auto-detected. The agent must read these files and add them to the graph
manually. This is a known gap for the experimental Django stack.

## Not a runnable app

Like `example-todo-app`, this omits migrations, settings for production,
tests, and the React frontend. Use it as a detector fixture, not a
starter template.
