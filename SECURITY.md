# Security and Privacy

This document describes exactly what the project-defense-skill does and does
not do with your code, network, and machine. The short version: everything
stays local unless you explicitly give a GitHub URL.

## What the skill reads

- Source files in the folder you opened (or the GitHub repo you named)
- The project's `package.json`, `requirements.txt`, `pyproject.toml`, and
  other manifest files
- Test files and configuration files
- README, LICENSE, and any other documentation

## What the skill avoids

- `.env`, `.env.local`, `.env.production`, and any other env files
- `*.pem`, `*.key`, `id_rsa*`, `*.secret`, `*.token` (private keys and tokens)
- `node_modules/`, `__pycache__/`, `dist/`, `build/`, `venv/`, `vendor/`
  (dependency and build directories)
- `.git/`, `.svn/`, `.hg/` (version control internals)

If you want the skill to inspect something it normally avoids (e.g., to
verify a specific config in `.env.example`), say so explicitly and it will
read just that file.

## Network behavior

| Trigger | Network activity |
|---|---|
| You give a **local path** | None. The skill does not connect to any network. |
| You give a **GitHub URL** | One HTTPS GET to `https://api.github.com/repos/<owner>/<repo>/tarball` to fetch the repo as a tarball. The tarball goes to a temp dir, is scanned, and the temp dir is auto-deleted on exit. |

**The skill does not:**

- Send your code, your file tree, or any metadata to any server other than the
  one tarball fetch above
- Phone home, log telemetry, or check for updates
- Store or transmit credentials, tokens, or environment variables
- Call any third-party API (OpenAI, Anthropic, etc.) — the agent you are
  using makes those calls, not the skill

## File system behavior

| Trigger | Filesystem activity |
|---|---|
| Local analysis | Writes only to `<analyzed-repo>/.project-defense/` |
| GitHub URL analysis | Writes to a temp dir (`/tmp/pdc-fetch-XXXXXX/` on Linux, equivalent on macOS/Windows). The temp dir is auto-cleaned on exit. Use `--keep <dir>` to persist the fetched copy. |

**The skill does not:**

- Push code to any remote
- Delete files outside `.project-defense/` (local mode) or the temp fetch dir
  (GitHub URL mode)
- Install packages (`pip install`, `npm install`, etc.)
- Modify any file in the analyzed repo's source tree

## Scripts you should review

All three scripts are short, stdlib-only, and readable in 5-10 minutes each:

- `scripts/scan_repository.py` — reads the file tree and dependency manifests
- `scripts/detect_code_facts.py` — reads JS/TS/Python source files for
  patterns (routes, components, models, auth calls)
- `scripts/validate_graph.py` — validates JSON against the schema
- `scripts/fetch_repository.py` — only used in GitHub URL mode. Downloads a
  tarball over HTTPS to a temp dir, with size cap and tar-slip protection.

**Do not run any code on your machine that you have not read.**

## Reporting a security issue

If you find a way for the skill to exfiltrate data, access files outside the
intended scope, or otherwise violate the contracts above, please open a
GitHub issue marked `security` or contact the maintainer directly.

## Threat model

The skill is designed against:

- **Accidental credential exposure** — secrets are filtered from scanning
- **Path traversal in tarballs** — `fetch_repository.py` validates every
  tarball member against the extraction root
- **Resource exhaustion** — tarball download is capped at 500 MB by default
- **Host injection** — only `github.com`, `api.github.com`, and
  `codeload.github.com` are accepted in v1

The skill is **not** designed against:

- A malicious agent that has been hijacked via prompt injection in a
  fetched repo's source code — review the agent's output, especially
  any file paths or commands it proposes to run
- A malicious fork of the skill itself — install only from the official
  source, review `scripts/*.py` before running

## Changelog

- v1.0 — initial release
