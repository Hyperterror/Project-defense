# Scope

What this skill is, what it deliberately is not, and the bar an idea has to
clear before it belongs here.

## What it is

A **defense coach**: it reads the user's own repository, verifies what it
found with the user, and produces the material a candidate needs to defend
that project in an interview — architecture and data-flow docs, a domain
glossary, a question bank, scored mock interviews, practice challenges, and a
spaced review schedule.

The differentiating rule is the verification loop: nothing is documented until
the analysis has been shown to the user and confirmed. Everything else exists
to make that loop worth the user's time.

## What it is not

| Not this | Why not |
|---|---|
| A generic code explainer | Explanations without project-specific evidence are what a candidate already gets from an LLM. The value here is `file:line` evidence and the score. |
| A linter or static-analysis suite | `scan_repository.py` and `detect_code_facts.py` are regex heuristics over ~8k lines of stdlib Python. Coverage is bounded on purpose; the user's confirmation is what closes the gap. |
| A test generator | It writes starter files and checks, not a test suite for the user's repo. |
| A code editor | It never modifies the analyzed repo outside `.project-defense/`, never rewrites source, and never installs packages. See [SECURITY.md](SECURITY.md). |
| A multi-repo or monorepo analyzer | One repository per run, identified by `session_identity` (path + remote + HEAD). |
| An LLM-backed scorer | Scoring is a rubric the agent reads, with a deterministic keyword fallback that is always labelled `scored_by: heuristic`. There is no hidden model call. |
| A truth oracle | Uncertainties stay `UNVERIFIED` in the graph. Guessing is the failure mode this skill exists to prevent. |

## The bar for a change

A proposal or bug report is worth acting on when **both** hold:

1. **Observed failure.** It describes something that went wrong in a real run:
   what was run, what the skill did, and what was expected. "It would be nicer
   if..." does not clear this bar.
2. **Fits the constraints.** Stdlib-only Python 3.8+, no network calls beyond
   the single GitHub tarball fetch, no modification of the analyzed repo, and
   no claim that lacks evidence.

On ties, prefer the fix with a regression test in `tests/` — every defect fixed
in this repo so far is pinned by one.

## Coverage model

Detection has two tiers, documented in the README:

- **Tier 1 (framework-aware)**: Express, Next.js, FastAPI, Flask, Django/DRF. The
  detector models the framework, so route prefixes, mounts, routers and
  permission classes resolve to the real endpoint.
- **Tier 2 (pattern packs)**: Go, Ruby, PHP, Java, C#, Rust, Kotlin, Elixir and
  Prisma, via `detect_stack_generic.py`. One pack per ecosystem, each resolving
  the prefixes that change a path.

Beyond that, the honest fallback is an uncertainty, not a guess: an
unrecognised stack produces *"which framework serves this API?"* in the graph, a
stderr warning from the question bank, and a generic interview that the user is
told is generic. Adding a pack is the right way to widen coverage; inventing a
route is not. Every pack needs tests that assert both a positive detection and
the absence of a false positive, because a pack that over-matches is worse than
no pack at all — it produces confident questions about routes that do not exist.

## Already decided (do not re-propose)

- **Tree-sitter / any pip dependency.** Extraction fidelity is worth improving,
  but the install-free promise is worth more; heuristics plus user confirmation
  is the chosen trade-off.
- **Hard cap on the number of questions.** The verification loop and review
  plan are open-ended by design; the escape hatch is the user saying "stop",
  not a counter.
- **Automatic scoring without rubrics.** A number without `scoring_levels` is
  indistinguishable from a guess, and the readiness report would become
  unfalsifiable.
- **Rendering Mermaid to images.** The `.mmd` files are the artifact; the
  renderer is the user's tool.
- **Hand-editing `project-graph.json` during Phase 4.** The graph is regenerated
  from facts on every run, so a hand edit is lost on the next rebuild. Phase 4
  decisions go through `save_corrections.py` and are re-applied by
  `build_graph.py`.
- **A full parser per language.** Tier 2 packs are deliberately pattern-based.
  Where a pattern cannot see the truth (dynamic routes, computed mounts, heavy
  metaprogramming), the pack says nothing and the uncertainty asks the user.
