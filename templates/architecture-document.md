# {{DOCUMENT_TITLE}}

> **Project:** {{PROJECT_NAME}}
> **Generated:** {{DATE}}
> **Source:** `.project-defense/project-graph.json` (verified entries only)

---

## 1. Project Purpose

{{PURPOSE}}

---

## 2. Technology Stack

| Layer | Technology | Version / Notes |
|-------|------------|-----------------|
{{#each STACK}}
| {{layer}} | {{tech}} | {{notes}} |
{{/each}}

---

## 3. Main Components

### 3.1 Frontend

{{#if FRONTEND_PAGES}}
**Pages:**
{{#each FRONTEND_PAGES}}
- **{{name}}** — {{details.description}} (`{{evidence.file}}:{{evidence.lines[0]}}`)
{{/each}}
{{/if}}

{{#if FRONTEND_COMPONENTS}}
**Components:**
{{#each FRONTEND_COMPONENTS}}
- **{{name}}** — {{details.type}} (`{{evidence.file}}:{{evidence.lines[0]}}`)
{{/each}}
{{/if}}

{{#if FRONTEND_STATE}}
**State Management:**
{{#each FRONTEND_STATE}}
- **{{name}}** — {{details.library}} (`{{evidence.file}}:{{evidence.lines[0]}}`)
{{/each}}
{{/if}}

{{#if FRONTEND_API}}
**API Calls:**
{{#each FRONTEND_API}}
- **{{name}}** → `{{details.method}} {{details.endpoint}}` (`{{evidence.file}}:{{evidence.lines[0]}}`)
{{/each}}
{{/if}}

### 3.2 Backend

{{#if BACKEND_ROUTES}}
**Routes:**
{{#each BACKEND_ROUTES}}
- **{{method}} {{path}}** → {{handler}} {{#if middleware}}[middleware: {{#each middleware}}{{.}}{{#unless @last}}, {{/unless}}{{/each}}]{{/if}} (`{{evidence.file}}:{{evidence.lines[0]}}`)
{{/each}}
{{/if}}

{{#if BACKEND_MIDDLEWARE}}
**Middleware:**
{{#each BACKEND_MIDDLEWARE}}
- **{{name}}** — {{details.purpose}} (`{{evidence.file}}:{{evidence.lines[0]}}`)
{{/each}}
{{/if}}

{{#if BACKEND_CONTROLLERS}}
**Controllers:**
{{#each BACKEND_CONTROLLERS}}
- **{{name}}** — {{details.responsibility}} (`{{evidence.file}}:{{evidence.lines[0]}}`)
{{/each}}
{{/if}}

{{#if BACKEND_SERVICES}}
**Services:**
{{#each BACKEND_SERVICES}}
- **{{name}}** — {{details.responsibility}} (`{{evidence.file}}:{{evidence.lines[0]}}`)
{{/each}}
{{/if}}

### 3.3 Data Layer

{{#if DATA_MODELS}}
**Models:**
{{#each DATA_MODELS}}
- **{{name}}**
  {{#each fields}}
  - `{{name}}: {{type}}` {{#if required}}*(required)*{{/if}} {{#if unique}}*(unique)*{{/if}} {{#if indexed}}*(indexed)*{{/if}}
  {{/each}}
  (`{{evidence.file}}:{{evidence.lines[0]}}`)
{{/each}}
{{/if}}

{{#if DATA_RELATIONSHIPS}}
**Relationships:**
{{#each DATA_RELATIONSHIPS}}
- **{{from}}** —{{type}}→ **{{to}}** (`{{evidence.file}}:{{evidence.lines[0]}}`)
{{/each}}
{{/if}}

### 3.4 Authentication

**Strategy:** {{AUTH_STRATEGY}}
**Token Handling:** {{AUTH_TOKEN_HANDLING}}

{{#if AUTH_PROTECTED}}
**Protected Routes:**
{{#each AUTH_PROTECTED}}
- **{{name}}** (`{{evidence.file}}:{{evidence.lines[0]}}`)
{{/each}}
{{/if}}

---

## 4. {{LIFECYCLE_OR_STEPS}}

{{#if LIFECYCLE_STEPS}}
{{#each LIFECYCLE_STEPS}}
### Step {{@index}}: {{title}}

{{description}}

**Code:** `{{evidence.file}}:{{evidence.lines[0]}}`
```{{LANGUAGE}}
{{excerpt}}
```
{{/each}}
{{/if}}

---

## 5. Key Design Decisions (Verified Only)

{{#each DECISIONS}}
- **{{title}}** — {{rationale}} [`{{evidence.file}}:{{evidence.lines[0]}}`]
{{/each}}

---

## 6. Interview-Ready Summary

{{SUMMARY}}

> *Memorize this: 3-4 sentences you can deliver in 30 seconds.*

---

## 7. Evidence Appendix

| Claim | File | Lines | Status |
|-------|------|-------|--------|
{{#each EVIDENCE_TABLE}}
| {{claim}} | {{file}} | {{lines}} | {{status}} |
{{/each}}

> ⚠️ **UNVERIFIED entries** appear above with status `UNVERIFIED`. These need human clarification before relying on them.