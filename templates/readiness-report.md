# Readiness Report

> Template for `docs/readiness-report.md` (Phase 10). Every claim carries the
> evidence reference from the graph: `{file}:{lines}`. Delete this note before
> delivering the report, and delete any section you cannot fill with evidence
> rather than leaving it empty.

**Repository:** `<owner/repo>` @ `<commit>`
**Session:** `<session-id>` — `<date>`
**Graph built:** `<analyzed_at>` — freshness: `<fresh|stale (N commits behind)>`

---

## 1. Verdict

**<Ready | Nearly ready | Not ready>** — `<one sentence a candidate could repeat in the interview>`

**Overall score:** `<0.00-1.00>` — based on **`<K>` of `<N>` questions**, covering
`<weight_covered>` of the rubric.

> If `weight_covered` is below 0.6, say so in this sentence. A score over 40% of
> the interview is a signal; a score over 10% is an anecdote. Never present the
> number without the coverage that produced it.

**Reliability:** `<agent-scored | mixed | heuristic-only>` — see the note from
`assess.py finish`. If it is not `agent-scored`, the numbers came from keyword
matching and must be labelled as such wherever they appear.

---

## 2. What held up

One row per category that scored `>= 0.5`. Say what the candidate actually
demonstrated, not just the category name.

| Category | Score | Evidence they produced |
|---|---|---|
| `<Architecture>` | `<0.83>` | `<the specific mechanism they explained, with file:lines>` |

---

## 3. Critical gaps

Anything with a concept score `< 1.5/3`. Each gap needs a file reference — a gap
without a pointer is a feeling, not a finding.

| Gap | Concept score | Where it lives | What was missing |
|---|---|---|---|
| `<token refresh>` | `<0.0/3>` | `<blog/views.py:23-35>` | `<no refresh path; a client with an expired token cannot recover>` |

---

## 4. Unverified items

Claims the analysis could not confirm from code. Each one is a question the
candidate must answer, and none may be silently dropped.

- [ ] `<claim>` — `<why it could not be verified>` — `<what would settle it>`

---

## 5. If the interview were tomorrow

Three actions, most valuable first. Each is concrete enough to do in one sitting.

1. **<Action>** — `<file:lines to read first>` — `<how you will know it is done>`
2. **<Action>** — `<...>`
3. **<Action>** — `<...>`

---

## 6. Next session

`python scripts/plan_review.py . --write` scheduled `<K>` questions for review;
the weakest were `<q-id>, <q-id>`. Suggested focus for the next round:
`<category>` and `<category>` — the two categories with the lowest coverage, not
just the lowest scores.
