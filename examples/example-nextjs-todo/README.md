# Example Next.js Todo (App Router)

A minimal Next.js 14 + Supabase todo app. **Experimental stack** — the
skill's detectors don't yet understand Next.js conventions like
`app/api/.../route.ts` files, App Router server components, or Supabase
auth. The agent runs the detectors, gets partial output, and fills in
the rest during the verification loop.

## Try the skill on this

```bash
python3 scripts/scan_repository.py examples/example-nextjs-todo
python3 scripts/detect_code_facts.py examples/example-nextjs-todo
python3 scripts/build_graph.py examples/example-nextjs-todo
```

The detector should find:
- 1 React component (`TodoList` from `app/page.tsx`)
- 2 fetch API calls (GET and POST `/api/todos`)
- 3 env vars (NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY)

## What's missing (manual work in Phase 4)

- Next.js App Router routes (file-based routing under `app/api/`) are
  not auto-detected
- Supabase auth is not detected as an "auth strategy" (no JWT.sign in
  this code, just Supabase's built-in)
- The agent must read `app/api/todos/route.ts` and `[id]/route.ts` and
  add to `backend.routes`

## Not a runnable app

This is a fixture for detector testing. It omits the Supabase project
itself, migrations, auth UI, and the `next.config.js` / `tsconfig.json`
boilerplate.
