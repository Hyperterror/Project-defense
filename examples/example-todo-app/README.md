# Example Todo App

A small full-stack todo app used to exercise the project-defense-skill
detectors. It is intentionally small but covers:

- Express routes (`GET/POST/PATCH/DELETE /api/todos`, `POST /api/auth/login`, `POST /api/auth/register`)
- Express middleware (`cors`, `express.json`, custom `authMiddleware`)
- Mongoose models (`User`, `Todo`) with proper schema definitions
- React components (`TodoList`, `TodoItem`, `LoginPage`)
- Custom React hook (`useAuth`)
- API calls from frontend (axios with `Bearer` token)
- JWT authentication (jsonwebtoken) with bcrypt password hashing
- Environment variables (`PORT`, `MONGODB_URI`, `JWT_SECRET`)

## Try the skill on this

```bash
# From the project-defense-skill root
python3 scripts/scan_repository.py examples/example-todo-app
python3 scripts/detect_code_facts.py examples/example-todo-app
```

The detector should find:
- 2 Mongoose models (User, Todo)
- 5 Express routes
- 3 Express middleware registrations
- 3 React components
- 1 React hook (useAuth)
- 5+ axios API calls
- JWT.verify in server/middleware/auth.js
- bcrypt.hash and bcrypt.compare in server/routes/auth.js
- 3 environment variables

## This is NOT a runnable app

The example omits `node_modules`, Vite config, MongoDB setup, and tests.
It exists to feed the detectors with realistic code patterns so the
end-to-end workflow can be exercised. To turn it into a runnable app,
add the missing pieces or use it as a reference for what a real project
should look like.
