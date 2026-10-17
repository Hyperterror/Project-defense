# Core Logic — {{DOCUMENT_TITLE}}

> **Project:** {{PROJECT_NAME}}
> **Generated:** {{DATE}}
> **Source:** `.project-defense/project-graph.json` (verified entries only)

---

## 1. Overview

This document covers the project's core algorithms, business rules, and the
non-obvious logic that an interviewer will dig into. If your project does
something specific in a clever way (or a non-obvious way), it goes here.

**Core features covered:**
{{#each CORE_FEATURES}}
- {{name}} — `{{evidence.file}}:{{evidence.lines.[0]}}`
{{/each}}

---

## 2. Core Feature: {{FEATURE_1_NAME}}

### 2.1 What it does
{{FEATURE_1_DESCRIPTION}}

### 2.2 Why this approach
{{FEATURE_1_RATIONALE}}

**Evidence:** `{{FEATURE_1_EVIDENCE}}`

### 2.3 Step-by-step
1. **Input:** {{FEATURE_1_STEP_1_INPUT}}
2. **Validation:** {{FEATURE_1_STEP_2_VALIDATION}}
3. **Main logic:** {{FEATURE_1_STEP_3_LOGIC}}
4. **Side effects:** {{FEATURE_1_STEP_4_SIDE_EFFECTS}}
5. **Output:** {{FEATURE_1_STEP_5_OUTPUT}}

### 2.4 Edge cases handled
{{#each FEATURE_1_EDGE_CASES}}
- **{{case}}** — handled by: `{{handled_in}}`
{{/each}}

### 2.5 Edge cases NOT handled (be honest)
{{#each FEATURE_1_GAPS}}
- **{{gap}}** — risk: {{risk}}
{{/each}}

---

## 3. Core Feature: {{FEATURE_2_NAME}}

### 3.1 What it does
{{FEATURE_2_DESCRIPTION}}

### 3.2 Why this approach
{{FEATURE_2_RATIONALE}}

**Evidence:** `{{FEATURE_2_EVIDENCE}}`

### 3.3 Algorithm
```
{{FEATURE_2_ALGORITHM_PSEUDOCODE}}
```

### 3.4 Complexity
- **Time:** {{FEATURE_2_TIME_COMPLEXITY}}
- **Space:** {{FEATURE_2_SPACE_COMPLEXITY}}

---

## 4. Business Rules

These are the "tribal knowledge" rules that are easy to break if you don't
know they exist.

| Rule | Where it lives | Why | What breaks if violated |
|------|----------------|-----|--------------------------|
{{#each BUSINESS_RULES}}
| {{rule}} | `{{evidence.file}}:{{evidence.lines.[0]}}` | {{why}} | {{consequence}} |
{{/each}}

---

## 5. Invariants

Things that must always be true in the system.

{{#each INVARIANTS}}
- **{{invariant}}** — maintained by: `{{maintained_by}}`
{{/each}}

---

## 6. Common Failure Modes

| What goes wrong | How the code handles it | Where |
|------------------|------------------------|-------|
{{#each FAILURE_MODES}}
| {{what}} | {{handling}} | `{{evidence.file}}:{{evidence.lines.[0]}}` |
{{/each}}

---

## 7. Things You'd Refactor

Be honest here — interviewers respect self-awareness.

{{#each REFACTOR_CANDIDATES}}
- **{{what}}** — why: {{why}}, suggested fix: {{fix}}
{{/each}}

---

## 8. Interview-Ready Summary

> *Memorize this: 2-3 sentences on the most interesting/clever/non-obvious
> thing your project does.*

{{SUMMARY}}

---

## 9. Evidence Appendix

| Claim | File | Lines | Status |
|-------|------|-------|--------|
{{#each EVIDENCE_TABLE}}
| {{claim}} | {{file}} | {{lines}} | {{status}} |
{{/each}}

> ⚠️ **UNVERIFIED entries** appear above with status `UNVERIFIED`. These need human clarification before relying on them.
