# Data Flow — {{DOCUMENT_TITLE}}

> **Project:** {{PROJECT_NAME}}
> **Generated:** {{DATE}}
> **Source:** `.project-defense/project-graph.json` (verified entries only)

---

## 1. Overview

This document traces how data moves through the system from user action to
persistent storage and back. It is the reference for explaining "what
happens when..." questions in an interview.

**Primary user journey traced:** {{PRIMARY_USER_JOURNEY}}

---

## 2. Data Flow Diagram

```mermaid
{{DATA_FLOW_DIAGRAM}}
```

The diagram is generated from `.project-defense/diagrams/data-flow.mmd`.
View the raw Mermaid source for the exact syntax.

---

## 3. Step-by-Step Lifecycle

### Step 1: User Action
- **Actor:** {{ACTOR_1}}
- **Action:** {{ACTION_1}}
- **Data produced:** {{DATA_1}}
- **Code:** `{{EVIDENCE_1}}`

### Step 2: Frontend Handling
- **Actor:** {{ACTOR_2}}
- **Action:** {{ACTION_2}}
- **Data transformation:** {{DATA_TRANSFORM_2}}
- **Code:** `{{EVIDENCE_2}}`

### Step 3: Network Request
- **Method:** {{METHOD_3}}
- **Endpoint:** {{ENDPOINT_3}}
- **Headers / auth:** {{HEADERS_3}}
- **Payload shape:** {{PAYLOAD_3}}
- **Code:** `{{EVIDENCE_3}}`

### Step 4: API Route
- **Route handler:** {{ROUTE_HANDLER_4}}
- **Middleware chain:** {{MIDDLEWARE_4}}
- **Code:** `{{EVIDENCE_4}}`

### Step 5: Controller / Service
- **Responsibility:** {{RESPONSIBILITY_5}}
- **Data validation:** {{VALIDATION_5}}
- **Code:** `{{EVIDENCE_5}}`

### Step 6: Data Layer
- **Model / collection:** {{MODEL_6}}
- **Operation:** {{OPERATION_6}} (read / write / update / delete)
- **Indexes used:** {{INDEXES_6}}
- **Code:** `{{EVIDENCE_6}}`

### Step 7: Response
- **Status code:** {{STATUS_7}}
- **Response shape:** {{RESPONSE_7}}
- **Error cases:** {{ERROR_CASES_7}}
- **Code:** `{{EVIDENCE_7}}`

### Step 8: Frontend Update
- **State mutation:** {{STATE_UPDATE_8}}
- **Re-render / side effect:** {{RENDER_8}}
- **Code:** `{{EVIDENCE_8}}`

---

## 4. State Transitions

| State | Trigger | Next State | Code |
|-------|---------|------------|------|
{{#each STATE_TRANSITIONS}}
| {{from}} | {{trigger}} | {{to}} | `{{evidence.file}}:{{evidence.lines.[0]}}` |
{{/each}}

Common state transitions to know:
- `unauthenticated` → `authenticated` (on successful login)
- `authenticated` → `expired` (on token expiration)
- `loading` → `success` / `error` (on API resolution)

---

## 5. Async and Side-Effect Flows

{{#each ASYNC_FLOWS}}
### {{name}}
- **Trigger:** {{trigger}}
- **Side effect:** {{side_effect}}
- **Code:** `{{evidence.file}}:{{evidence.lines.[0]}}`
- **Failure mode:** {{failure_mode}}
{{/each}}

---

## 6. Error Propagation

| Error Source | Caught Where | Response | User Feedback |
|--------------|--------------|----------|---------------|
{{#each ERROR_PATHS}}
| {{source}} | {{caught_at}} | {{response}} | {{user_feedback}} |
{{/each}}

---

## 7. Interview-Ready Summary

> *Memorize this: 2-3 sentences describing one full request lifecycle.*

{{SUMMARY}}

---

## 8. Evidence Appendix

| Step | File | Lines | Status |
|------|------|-------|--------|
{{#each EVIDENCE_TABLE}}
| Step {{step}} | {{file}} | {{lines}} | {{status}} |
{{/each}}

> ⚠️ **UNVERIFIED entries** appear above with status `UNVERIFIED`. These need human clarification before relying on them.
