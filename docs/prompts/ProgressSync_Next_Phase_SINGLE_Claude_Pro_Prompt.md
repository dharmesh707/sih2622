# ProgressSync AI (SIH26122) — Single Claude Pro Implementation Prompt

You are the **single implementation agent** responsible for completing the current ProgressSync AI (SIH26122) repository.

One person will run this entire task in **one Claude Pro + Claude Code session**.

You have already been given the project context, plugin setup, ultimate implementation prompt, and the **25 September 2026 Final Audit Report**.

Your job is now to take the audited repository from its current state to a **stable, demo-ready SIH prototype**.

---

# 0. CRITICAL OPERATING RULES

## Work in this order

1. Inspect current repository and audit state.
2. Fix correctness/safety bugs.
3. Fix ML reproducibility.
4. Complete React/SIH-critical workflow.
5. Fix schedule/dependency/CPM intelligence.
6. Fix analytics/institutional memory.
7. Fix Time Agent.
8. Fix terminology source.
9. Harden tests and benchmark.
10. Perform browser E2E and release verification.

Do not jump ahead if a critical earlier phase is broken.

## Do NOT expand scope

For this sprint, do **NOT** add:

- Supabase
- PostgreSQL migration
- mobile app
- XER import
- 3D visualization
- enterprise SSO
- production OCR infrastructure
- production ASR infrastructure
- complex MLOps

These are not allowed to block the core SIH workflow.

## Preserve working logic

Do NOT rewrite the validated matching/scoring/CPM architecture unless a specific verified defect requires it.

Do not replace working modules merely for stylistic reasons.

## Testing rule

After every meaningful phase:

1. Run relevant tests/builds.
2. Verify the actual result.
3. Update `PROGRESS.md`.
4. Continue only after recording the result.

Never fabricate a result.

## Data rule

Keep separate:

- development data
- training data
- validation/tuning data
- held-out test data
- benchmark data
- demo/seed data

Never tune on the final held-out set.

## Safety rule

Preserve the meaning of:

- `AUTO_MATCHED`
- `REVIEW_REQUIRED`
- `UNMATCHED`

Never allow uncertainty to be silently converted into a schedule update.

---

# 1. VERIFIED CURRENT STATE FROM THE 25 SEP AUDIT

The audit established:

### Working

- Backend happy path: ingest → extract → score → route → confirm → audit → CPM.
- React/Vite builds.
- React uses real backend APIs.
- Chrome DevTools MCP works.
- Ponytail, React, Vite and Run Verify plugins work.
- MiniLM + current matching pipeline works when the model is locally cached.
- Unknown activity can be preserved as UNMATCHED in normal API flow.
- Existing benchmark routing numbers reproduce.

### Confirmed problems

### High priority

1. `norm()` globally changes every `o` to `0`, breaking:
   - spool
   - boltup
   - hydrotest
   - erection
   - foundation
   - concrete
   - rotating
   - completed/completion inference
   - CT103
   - some unknown-work-package signals

2. Confirm/reject state handling is unsafe:
   - approve → reject → approve can produce multiple writes/audit rows
   - final state can disagree with schedule state

3. MiniLM fails on a clean machine:
   - `local_files_only=True`
   - no documented provisioning/download path
   - clean-machine tests fail

4. `project_id=1` is hardcoded in matching/confirmation:
   - multi-project behavior is incorrect
   - audit can receive the wrong project ID

5. React has no confirm path for AUTO_MATCHED.

6. React review shows only rank-1:
   - no candidate comparison
   - no alternate selection/reassign

7. UNMATCHED can still expose an “Approve top candidate” shortcut.

### Important

8. No Gantt/timeline view.

9. Imported dependency relationships are not being built into the CPM graph.

10. CPM does not change meaningfully from confirmed actuals.

11. No real planned-vs-actual variance.

12. `at_risk` is not calculated.

13. Delay causes have no write path.

14. Institutional memory uses planned duration as actual duration.

15. Time Agent has no real multi-turn clarification.

16. YAML terminology map is not the actual source of truth.

17. Benchmark is too small/easy and does not adequately exercise:
   - unknowns
   - terminology
   - realistic field paraphrases
   - discipline filtering

18. Backend tests are weak for several safety/edge cases.

19. No proper frontend/browser E2E suite.

20. Demo/release reset and clean-machine setup are incomplete.

---

# 2. PHASE 0 — RE-AUDIT BEFORE CODING

Before modifying anything:

1. Read the current repository.
2. Read:
   - `2_ULTIMATE_PROMPT_FINAL.md`
   - final plugin setup MD
   - `PROGRESS.md`
   - latest audit if it exists in the repository
3. Confirm current branch and commit.
4. Confirm the actual database currently used.
5. Confirm frontend/backend entry points.
6. Confirm current tests and benchmark commands.

Do not modify anything during this quick verification.

Then create/update `PROGRESS.md` with:

- phase
- status
- tests run
- known issues
- files changed

---

# 3. PHASE 1 — FIX CORRECTNESS AND SAFETY FIRST

## 3.1 Fix `norm()`

The current implementation globally replaces `o` with `0`.

Change this so OCR-style digit correction happens only in appropriate identifier contexts.

Do NOT alter ordinary words.

Add regression tests for:

- `spool`
- `boltup`
- `hydrotest`
- `erection`
- `foundation`
- `concrete`
- `rotating`
- `completed`
- `CT103`
- `unknown work package`

Expected:

- terminology matching works,
- discipline detection works,
- completion inference works where intended,
- CT103 remains identifiable.

Run all backend tests.

---

## 3.2 Fix confirmation state transitions

Implement a safe state machine.

At minimum:

- approved event cannot be silently rejected while leaving schedule changes intact,
- duplicate confirmation is rejected or idempotent,
- reject → confirm behavior is deterministic,
- audit matches real state.

Add tests:

- confirm → confirm
- confirm → reject
- reject → confirm
- reject nonexistent event
- confirm nonexistent activity
- wrong-project confirmation

---

## 3.3 Fix missing entity handling

Return clean 4xx errors instead of 500s for:

- nonexistent event
- nonexistent activity
- wrong project ownership

Add tests.

---

## 3.4 Fix project scoping

Remove all hardcoded project 1 assumptions.

Project ID must flow through:

```text
field report
→ execution event
→ candidate retrieval
→ review
→ confirmation
→ schedule update
→ audit
→ analytics
→ memory
```

Add a multi-project test with similar-looking activities.

---

# 4. PHASE 2 — MAKE MINILM REPRODUCIBLE

The semantic model is part of the working pipeline.

Do NOT fake a semantic fallback.

Implement one clean provisioning approach:

- setup script, OR
- documented one-time model download/cache command.

Requirements:

- model name/version documented,
- provisioning path documented,
- clean-machine failure message is useful,
- README updated,
- test setup documented.

Also remove stale documentation claiming a deterministic proxy fallback if it no longer exists.

Run the clean test flow again.

---

# 5. PHASE 3 — COMPLETE THE REACT SIH WORKFLOW

Use the real backend. No fake success states.

## 5.1 AUTO_MATCHED

The React UI must show:

- activity code
- activity description
- evidence
- confidence
- score/reranker information
- confirm action

After confirm show:

- schedule change
- audit result
- CPM result

---

## 5.2 REVIEW_REQUIRED

Show top-N candidates.

Each candidate should include:

- activity code
- description
- discipline
- location where available
- identifier score
- lexical score
- semantic score
- context score
- total/reranker score
- evidence

Allow explicit candidate selection.

---

## 5.3 REASSIGN

Planner can explicitly choose an alternate candidate.

Send the selected activity to the backend and record the human decision in audit.

---

## 5.4 UNMATCHED SAFETY

Remove any one-click action that can approve the top candidate for an UNMATCHED event.

For UNMATCHED:

- show why it is unmatched,
- preserve the observation,
- allow deliberate manual association only by explicit activity selection,
- record that human action.

---

## 5.5 GANTT

Implement a real schedule timeline.

At minimum show:

- activity code/name
- planned start
- planned finish
- actual start
- actual finish
- progress
- dependencies
- critical path
- at-risk state

Use live backend data.

Do not use fake/static timeline data.

---

# 6. PHASE 4 — FIX SCHEDULE + CPM INTELLIGENCE

## 6.1 Dependency import

Ensure schedule imports preserve actual dependency relationships.

Support the available fields:

- predecessor
- successor
- relationship
- lag

Persist them.

Build the CPM graph from those persisted relationships.

Validate cycles before accepting/importing a broken graph.

---

## 6.2 Actual-driven CPM

After confirmation:

1. snapshot current CPM,
2. apply actual update,
3. recompute,
4. compare old/new state.

Expose:

- project finish movement
- critical path entered/exited
- downstream float change
- at-risk activities
- milestone movement

Do not describe CPM as AI. It is deterministic project-controls mathematics.

---

## 6.3 At-risk

Implement a deterministic, documented rule.

Use real schedule/float/progress data.

Do not populate at-risk with a fake constant.

---

# 7. PHASE 5 — ANALYTICS + INSTITUTIONAL MEMORY

Implement/fix:

## Planned vs Actual

- start variance
- finish variance
- duration variance

## Productivity

- discipline
- activity type
- actual duration where available
- progress

## Delay causes

- structured cause field
- write path from UI/workflow
- counts/trends where data exists

## Institutional memory

Persist:

- project_id
- activity type
- planned duration
- actual start
- actual finish
- actual duration
- variance
- discipline
- location
- delay cause
- notes

Never use planned duration as actual duration.

If actual dates do not exist, leave actual duration null.

## History/similarity

Support searching previous activities/patterns using available metadata such as:

- discipline
- location
- activity type

Ensure results are project-aware where appropriate.

Expose these capabilities clearly in React.

---

# 8. PHASE 6 — TIME AGENT

Implement actual session persistence.

Required flow:

```text
Supervisor:
"XX102 started at 9."

System:
asks for missing/ambiguous context

Supervisor:
"Rack 3."

System:
resolves the same pending event
→ matching
→ decision
→ confirmation/update
→ audit
```

Requirements:

- `session_id` actually stores/retrieves session context,
- follow-up messages modify the same pending event,
- clarification is real, not canned,
- resolved events use the same pipeline as uploaded reports,
- final result is visible in UI,
- audit remains intact.

Voice can remain browser-based for prototype scope.

---

# 9. PHASE 7 — TERMINOLOGY SOURCE OF TRUTH

Make:

`data/terminology_map.v1.yaml`

the authoritative terminology source.

Requirements:

- read it at runtime,
- no conflicting hardcoded duplicate,
- API exposes current mappings,
- React can display mappings,
- matcher uses the loaded mappings.

Add tests for at least:

- `spool → piping segment`
- `rack 3 → R03`

and the project's other current terminology entries.

---

# 10. PHASE 8 — BENCHMARK HARDENING

Do NOT optimize metrics for appearance.

Fix the issues identified in the audit.

The benchmark must include:

- exact match
- synonym
- abbreviation
- typo/OCR-like noise
- near duplicate
- unknown activity
- missing timestamp
- wrong discipline
- granularity mismatch
- terminology-map case

Also:

1. Include unknown/unmatched cases in the held-out set.
2. Use realistic field paraphrases rather than copying activity descriptions.
3. Exercise terminology mapping.
4. Exercise discipline/project filtering.
5. Use the real production matching/routing path.
6. Make event/schedule dates reproducible.
7. Freeze held-out data before final evaluation.

Report actual metrics only.

Never call a small synthetic benchmark production accuracy.

---

# 11. PHASE 9 — TESTING

Add tests for the discovered bugs.

At minimum:

### Backend

- normalization
- terminology
- completion inference
- multi-project
- duplicate confirmation
- reject-after-approve
- missing event
- missing activity
- wrong-project activity
- dependency import
- dependency cycle
- actual duration
- at-risk

### Matching

- exact
- synonym
- abbreviation
- typo
- near duplicate
- unknown
- wrong discipline

### Time Agent

- session persistence
- clarification
- same-event continuation

### React/E2E

Use Chrome DevTools MCP.

Test:

1. confident AUTO_MATCHED
2. ambiguous REVIEW_REQUIRED
3. unknown UNMATCHED
4. Time Agent clarification
5. Gantt/CPM/analytics/memory close

---

# 12. PHASE 10 — RELEASE CLEANUP

Before declaring completion:

- clean demo database,
- reset/seed mechanism,
- pinned dependencies where practical,
- documented MiniLM provisioning,
- accurate README,
- accurate API docs,
- accurate demo instructions,
- no stale fallback claims,
- no stale static-frontend claims,
- no mock success states,
- no misleading metrics.

Run:

```bash
pytest -q
```

and:

```bash
cd frontend-react
npm ci
npm run build
```

Run the benchmark using the final frozen data.

Run browser E2E.

---

# 13. FINAL SIH DEMO CHECK

The complete demo must be able to show:

## Scenario A — Confident

```text
Field report
→ extraction
→ evidence
→ candidate
→ AUTO_MATCHED
→ confirm
→ schedule update
→ audit
→ CPM
```

## Scenario B — Ambiguous

```text
Vague report
→ REVIEW_REQUIRED
→ candidate comparison
→ planner selects alternate
→ confirmation
→ schedule update
```

## Scenario C — Unknown

```text
Unknown activity
→ UNMATCHED
→ preserved
→ no fabricated activity
```

## Scenario D — Time Agent

```text
Supervisor input
→ clarification
→ same session
→ same matching pipeline
→ update/audit
```

## Scenario E — Schedule intelligence

```text
Updated schedule
→ Gantt
→ critical-path impact
→ variance
→ delay causes
→ institutional memory
```

---

# 14. FINAL PROGRESS.md REQUIREMENT

Maintain:

```text
PROGRESS.md
```

After each phase record:

- Phase
- ✅ Done
- ⚠️ Partial
- ❌ Blocked
- Tests run
- Important changes
- Remaining issue

At the end include:

## Final Verified State

- backend
- database
- ML
- React
- Time Agent
- CPM
- Gantt
- analytics
- memory
- testing
- benchmark
- release

---

# 15. FINAL RESPONSE TO ME

At the end, do NOT just say "done".

Give a concise but evidence-based report:

## Completed
## Partially completed
## Blocked
## Tests actually run
## Benchmark actually run
## Browser verification actually run
## Files changed
## Remaining P0/P1/P2 issues
## Exact recommended next action

Include the exact commands used for:

- tests
- benchmark
- frontend build
- backend startup
- browser E2E

Do not report anything as verified unless it was actually verified.

# END OF PROMPT
