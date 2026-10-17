# Contributing to Project Defense Coach

Thanks for your interest in improving the skill! This is a small, scoped
project -- a folder of instructions, scripts, and templates that turn an
AI coding agent into a project-defense coach. Contributions that fit this
scope are very welcome.

## Code of conduct

Be kind. Assume good faith. Disagreements about design are fine; personal
attacks are not.

## What to contribute

The most useful contributions fall into these buckets, roughly in order of
impact:

### 1. Stack detectors (`scripts/detect_code_facts.py`)

The current detectors cover React, Express, and Mongoose (v1 supported
stack). Adding a new stack is the highest-impact change because it
unlocks real-world use for a whole category of projects.

To add a new stack:

1. **Pick a framework** (e.g., Next.js, Django, FastAPI, Flask, Rails).
2. **Find representative code patterns** -- look at 3-5 real open-source
   projects that use it. What's the canonical "hello world" for a route
   in this framework? A model? A component? A middleware?
3. **Write a regex** that catches the canonical pattern. The existing
   `RE_EXPRESS_ROUTE`, `RE_MONGOOSE_MODEL`, etc. are good references.
4. **Handle the equivalent of mount prefixes** -- Express has
   `app.use('/api/foo', router)`. Every framework has its own version
   (Next.js has `app/api/foo/route.ts`, Django has `urls.py` includes,
   FastAPI has `APIRouter` with prefix, etc.).
5. **Add a unit test** in `tests/test_skill.py` that creates a small
   fixture and asserts the detector finds the right things.
6. **Add the framework to the "experimental" list** in `SKILL.md` and
   `README.md`. Don't promise full support unless the detector is solid.

### 2. Templates (`templates/*.md`)

The three current templates (architecture, data-flow, core-logic) are
deliberately generic. Better templates for specific stacks (e.g., a
React-specific architecture template that includes a components-hierarchy
diagram) would be valuable.

To add a template:

1. Pick a doc that the existing templates are weak for.
2. Write a Handlebars-style template using `{{PLACEHOLDER}}` syntax.
3. Add an example output to `examples/<stack>/.project-defense/docs/`.
4. Document the template in `README.md`.

### 3. Example projects (`examples/`)

The §15 validation plan in the original Build Plan calls for "at least
five real repositories" before expanding stack support. Each example:

- Must be a small (under 500 lines), self-contained project in one
  supported or experimental stack
- Must exercise every detector the skill has for that stack
- Must include a `.project-defense/` showing the expected output
- Must have a `README.md` describing what to look for

Existing: `examples/example-todo-app/` (React + Express + MongoDB).
Wanted: Next.js, FastAPI, Django, Flask, Rails, React Native, etc.

### 4. Bug fixes and detector accuracy

The detectors are regex-based, which means they're brittle. False
positives and false negatives are the most common bug. If you find one:

1. Add a test case in `tests/test_skill.py` that reproduces it
2. Fix the regex
3. Verify the test now passes
4. Open a PR

### 5. Documentation

The README, SKILL.md, and instructions can always be clearer. Edits to
typos, unclear phrasing, and missing examples are welcome.

## What NOT to contribute

- **Platform code (web UI, database, accounts).** That's Phase 2 of the
  Build Plan and a separate project.
- **Private-repo fetcher.** Out of scope for v1 by design.
- **Multi-language support beyond what's listed in the Supported Stacks
  table.** Each language is a detector rewrite.
- **Replacement of the stdlib-only scripts with framework dependencies.**
  The scripts must work with just Python 3.8+.

## Development setup

```bash
# Clone
git clone https://github.com/<owner>/project-defense-skill
cd project-defense-skill

# Run the tests
python3 tests/test_skill.py

# Smoke-test the example
python3 scripts/scan_repository.py examples/example-todo-app
python3 scripts/detect_code_facts.py examples/example-todo-app
python3 scripts/build_graph.py examples/example-todo-app
python3 scripts/validate_graph.py examples/example-todo-app/.project-defense/project-graph.json
```

No build step, no dependencies, no virtualenv needed. If you find
yourself adding a `pip install` step to the README, propose it in an
issue first.

## Pull request process

1. Open an issue describing the change (for non-trivial work)
2. Fork the repo, create a branch (`feature/nextjs-detector`,
   `fix/express-route-typo`, etc.)
3. Make your change
4. Add a test in `tests/test_skill.py`
5. Run the test suite locally -- all 24+ tests must pass
6. Open a PR. The CI workflow will run on every push
7. Address review feedback. Small PRs are reviewed faster

## Style

- **Python:** PEP 8. Stdlib only. Type hints where they help. Comments
  explain *why*, not *what*.
- **Markdown:** sentence per line in headings, one blank line between
  sections, fenced code blocks with language tags.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`,
  `refactor:`).

## License

By contributing, you agree that your contributions will be licensed under
the MIT License (see `LICENSE`).
