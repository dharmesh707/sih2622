# ProgressSync AI (SIH26122) — Claude Code Plugin Setup

**Updated:** 24 September 2026  
**Purpose:** Minimal, project-focused Claude Code setup for the current ProgressSync AI prototype.

This setup is intentionally limited to the plugins that directly help with the remaining work:
- React/Vite frontend integration
- real browser verification
- run/build/test verification
- avoiding unnecessary rewrites and dependencies

Do **not** make Supabase, mobile, XER import, or other optional infrastructure part of the core setup unless the team explicitly decides to add them later.

---

## 1. Project assumptions

Current project priorities:

1. Preserve the working backend + ML matching pipeline.
2. Improve the database/data model where required.
3. Complete React/Vite integration with the existing FastAPI backend.
4. Complete review, Gantt, CPM-impact, analytics, audit and Time Agent UI.
5. Verify the full end-to-end workflow.
6. Clean the demo database and release environment.
7. Run the final tests and benchmark honestly.

The core matcher, semantic scoring, reranker and CPM logic should not be rewritten without evidence that something is broken.

---

# 2. Required plugins

## Plugin 1 — Ponytail

### Purpose

Ponytail pushes the coding agent toward reuse, the standard library, existing dependencies and the smallest implementation that solves the problem. It is useful here because the project is already substantial and the remaining work should be productization rather than unnecessary architectural expansion.

The project still needs robust validation, security and data-integrity work; Ponytail is not a reason to remove those safeguards.

### Install

```text
/plugin marketplace add DietrichGebert/ponytail
/plugin install ponytail@ponytail
```

Node.js must be available on PATH for its lifecycle hooks.

Verify:

```bash
node --version
```

Do not use an aggressive Ponytail mode for this project. Keep the default behavior.

---

# 3. Official Chrome DevTools MCP

## Purpose

Use this to test the real running web application instead of relying only on source-code reasoning.

Useful for:

- opening the React application
- uploading a field report
- testing AUTO_MATCHED / REVIEW_REQUIRED / UNMATCHED
- checking the review queue
- inspecting Gantt rendering
- checking console errors
- checking network/API failures
- verifying analytics and audit screens
- testing the final demo flow

### Install the official Chrome DevTools plugin

```text
/plugin marketplace add ChromeDevTools/chrome-devtools-mcp
/plugin install chrome-devtools-mcp@chrome-devtools-plugins
```

Restart Claude Code after installation.

Then verify:

```text
/skills
```

The official Chrome DevTools repository currently documents this plugin installation path.

If marketplace installation fails because GitHub HTTPS access is blocked, the project can use the documented CLI MCP fallback:

```bash
claude mcp add chrome-devtools --scope user npx chrome-devtools-mcp@latest
```

---

# 4. React plugin

## Purpose

The frontend is one of the highest-priority remaining workstreams.

Use the React plugin for:

- React component design
- state management patterns
- component composition
- React performance
- frontend maintainability
- clean React implementation instead of reverting to vanilla JS

### Install

```text
/plugin marketplace add pleaseai/claude-code-plugins
/plugin install react@pleaseai
```

---

# 5. Vite plugin

## Purpose

The project uses React + Vite, so this plugin helps with:

- Vite configuration
- development/build workflow
- Vite-related dependency decisions
- current Vite practices

### Install

```text
/plugin install vite@pleaseai
```

---

# 6. Run Verify plugin

## Purpose

This is especially useful during the final productization phase.

It is intended to help the coding agent:

- run the project
- build it
- execute verification steps
- drive the real application
- verify changes instead of merely claiming they should work

### Install

```text
/plugin install run-verify@pleaseai
```

Use it after meaningful code changes and before considering a feature complete.

---

# 7. Optional: plugin recommender

This is **not required** for ProgressSync.

Only install it if you want Claude to inspect project dependencies and recommend additional plugins automatically.

```text
/plugin install please-plugins@pleaseai
```

Then:

```text
/please-plugins:setup
```

Do not install extra plugins just because they are available. Every additional plugin should have a clear benefit to the current project.

---

# 8. Final recommended plugin set

For the current ProgressSync project, keep this stack:

```text
✅ ponytail
✅ chrome-devtools-mcp
✅ react
✅ vite
✅ run-verify
```

Optional:

```text
➕ please-plugins
```

Do not add anything else unless a real project need appears.

---

# 9. What NOT to install for the current sprint

## Supabase plugin — NOT required

The current plan is to keep the database architecture focused on PostgreSQL rather than making a Supabase migration a mandatory phase.

Do not install:

```text
supabase
```

unless the team explicitly decides that hosted Supabase services are actually needed.

The SIH prototype does not require Supabase specifically.

## React Native / mobile plugin — NOT required

Do not add a mobile app to the core sprint unless the web MVP is already green.

The SIH problem can be demonstrated with the web application and the Time Agent.

## XER-specific tooling — NOT required for the core sprint

XER support can be considered later. It should not delay:

- report ingestion
- spreadsheet ingestion
- matching
- planner review
- schedule update
- CPM
- Gantt
- analytics
- audit
- Time Agent
- testing

## 3D tooling — NOT required

The 3D view is outside the core SIH prototype requirement.

---

# 10. Installation sequence

Open Claude Code in the project repository.

### Step 1 — verify Node

```bash
node --version
```

### Step 2 — install Ponytail

```text
/plugin marketplace add DietrichGebert/ponytail
/plugin install ponytail@ponytail
```

### Step 3 — install official Chrome DevTools MCP

```text
/plugin marketplace add ChromeDevTools/chrome-devtools-mcp
/plugin install chrome-devtools-mcp@chrome-devtools-plugins
```

Restart Claude Code.

### Step 4 — install frontend/verification plugins

```text
/plugin marketplace add pleaseai/claude-code-plugins
/plugin install react@pleaseai
/plugin install vite@pleaseai
/plugin install run-verify@pleaseai
```

### Step 5 — reload

```text
/reload-plugins
```

### Step 6 — verify

```text
/plugin
```

Confirm the required plugins are visible.

Then:

```text
/skills
```

Confirm Chrome DevTools MCP skills are available.

---

# 11. Recommended Claude Code model

Do not hard-code an obsolete model version into the project instructions.

Use the current Opus model alias available in Claude Code:

```bash
claude --model opus
```

The exact model version may change over time; the project instructions should not depend on a hard-coded version number.

---

# 12. How the plugins fit ProgressSync

```text
                    Claude Code
                         |
        +----------------+----------------+
        |                |                |
    Ponytail          React/Vite      Run Verify
        |                |                |
  prevent waste      frontend work   run/build/test
        |                |                |
        +----------------+----------------+
                         |
                  Chrome DevTools
                         |
              real browser verification
                         |
                         v
               ProgressSync AI
                         |
        +----------------+----------------+
        |                |                |
     FastAPI          React/Vite      PostgreSQL
        |                |                |
        +----------------+----------------+
                         |
            ML matching + CPM + audit
```

---

# 13. Important project rules for Claude Code

Before changing anything:

1. Inspect the current repository.
2. Read the existing implementation before creating new architecture.
3. Reuse existing modules where they already solve the problem.
4. Do not rewrite validated ML matching or CPM logic without evidence.
5. Do not replace the database structure unnecessarily.
6. Preserve AUTO_MATCHED / REVIEW_REQUIRED / UNMATCHED semantics.
7. Never force an uncertain match.
8. Preserve auditability.
9. Use real backend data in React instead of mock success states.
10. Test every meaningful change.
11. Never fabricate benchmark numbers.
12. Never tune the final held-out test set.
13. Keep development, training, validation and held-out test data separate.
14. Prefer incremental changes over large rewrites.
15. Keep optional features from blocking the core SIH workflow.

---

# 14. Required final browser verification

Use Chrome DevTools to manually verify:

### Scenario A — Confident report

```text
Field report
→ extraction
→ candidate
→ confidence/evidence
→ AUTO_MATCHED
→ confirmation
→ schedule update
→ audit
→ CPM
```

### Scenario B — Ambiguous report

```text
Vague report
→ REVIEW_REQUIRED
→ candidate comparison
→ planner selection
→ schedule update
```

### Scenario C — Unknown activity

```text
Unknown activity
→ UNMATCHED
→ observation preserved
→ no fabricated activity_id
```

### Scenario D — Time Agent

```text
Supervisor text/voice
→ clarification if required
→ same matching pipeline
→ schedule/audit update
```

### Scenario E — Schedule intelligence

```text
Updated schedule
→ Gantt
→ critical-path impact
→ variance/analytics
→ institutional memory
```

---

# 15. Final verification command set

Run the project's actual commands from its README/package configuration.

At minimum verify:

```bash
# backend tests
pytest -q

# frontend install/build if applicable
npm install
npm run build
```

Do not assume these exact commands are correct for the repository if the current project documentation uses different commands. Inspect the repo first.

Then use Chrome DevTools to verify the running application manually.

---

# 16. Important note on plugins vs project architecture

Plugins are development tools. They should not change the SIH product architecture by themselves.

The product remains:

```text
Schedule import
      ↓
L5/L6 catalogue + dependencies
      ↓
Field report / spreadsheet / Time Agent
      ↓
Normalization + extraction
      ↓
Candidate retrieval
      ↓
ID + lexical + semantic + context matching
      ↓
Reranking
      ↓
AUTO_MATCHED / REVIEW_REQUIRED / UNMATCHED
      ↓
Planner action
      ↓
Schedule update
      ↓
Audit + CPM
      ↓
Gantt + Analytics + Institutional Memory
```

The plugins exist to help implement and verify this workflow, not to replace it.

---

# 17. Verification checklist

Before starting the final implementation session:

- [ ] Node is available on PATH
- [ ] Ponytail installed
- [ ] Chrome DevTools MCP installed
- [ ] React plugin installed
- [ ] Vite plugin installed
- [ ] Run Verify installed
- [ ] `/plugin` shows the expected plugins
- [ ] `/skills` shows Chrome DevTools skills
- [ ] Claude Code restarted after Chrome DevTools installation
- [ ] PostgreSQL/database decision is settled
- [ ] Current repository is cloned/opened
- [ ] Current context document is available
- [ ] Final implementation prompt is available
- [ ] No optional feature is allowed to block the SIH core workflow

---

## Verified sources

Claude Code plugin commands and the Ponytail installation were checked against the current project repositories.

Chrome DevTools MCP's official Claude Code installation was checked against the official ChromeDevTools repository.

The pleaseai marketplace currently lists the React, Vite, Run Verify and plugin-recommender plugins.

Keep this document as the project-specific setup reference and update it if the plugin stack changes.
