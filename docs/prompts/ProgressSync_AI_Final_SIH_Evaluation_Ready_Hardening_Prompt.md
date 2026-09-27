# ProgressSync AI — Final SIH Evaluation Readiness & Hardening Prompt

**Project:** ProgressSync AI  
**SIH Problem:** SIH26122 — Oil India Limited  
**Purpose:** Final hardening pass for SIH evaluation/demo deployment

---

## 0. Mission

Bring the current ProgressSync AI repository from the audited **demo-ready but not fully hardened** state to a **final SIH evaluation-ready build**.

This is a **targeted hardening pass**, not a redesign.

The latest audit verified that the core pipeline and five SIH scenarios (A–E) work end-to-end, but it found two high-severity data-integrity defects, one workflow reachability defect, and one extraction gap that should be fixed before the final evaluator-facing build.

### Non-negotiable principles

1. **Do not rewrite the validated matching/scoring architecture.**
2. **Do not lower matching thresholds just to increase AUTO_MATCHED volume.**
3. **Do not enable the reranker.** Keep the current reranker-disabled default because the held-out reranker benchmark currently produces silent errors.
4. **Uncertainty must go to review, never to a fabricated activity.**
5. **Do not silently infer completion/start from negated or future-tense language.**
6. **Never silently regress a completed activity.**
7. **Every schedule write must remain explicitly human-confirmed.**
8. **Preserve project scoping and the existing audit trail.**
9. **Do not replace deterministic CPM/project-controls calculations with AI.**
10. **Keep the existing frozen benchmark intact. Do not alter benchmark answers, manifests, or thresholds to improve the score.**
11. Prefer the smallest safe change that fixes the finding.
12. After every meaningful change, run the relevant tests before moving on.

---

# 1. Current audited baseline

The latest audit reports:

- Backend tests: **64 passed**
- Frontend clean install/build: **passed**
- `npm audit`: **0 vulnerabilities**
- Frozen held-out benchmark:
  - 84 cases
  - AUTO precision: **100% on 13 AUTO cases**
  - silent errors: **0**
  - top-1: **76.2%**
  - R@5: **92.1%**
  - unknown → UNMATCHED: **13/13**
  - cross-project candidates: **0**
- Five browser E2E SIH scenarios A–E pass.
- Reranker-on benchmark is unsafe and must remain disabled.
- Audited repository state contains uncommitted working-tree changes.

Treat these as the protected baseline.

Do not make changes that reduce the validated safety properties or accidentally reintroduce previously fixed bugs.

---

# 2. MUST-FIX #1 — F-01: Negation and future tense

## Problem

Current extraction can incorrectly interpret these kinds of statements as progress/start events:

- `not completed yet`
- `not started`
- `will be completed tomorrow`
- equivalent future/negative phrasing such as:
  - `yet to complete`
  - `pending completion`
  - `will start tomorrow`
  - `has not started`
  - `is not finished`
  - `not finished`
  - `completion is pending`

The current behavior can produce:
- `progress = 100`
- an inferred actual start
- `AUTO_MATCHED`
- a one-click confirmation that writes an incorrect schedule state

This is a **data-integrity bug**.

## Required behavior

Before extracting progress/start/finish from completion/start verbs:

### A. Detect negation and future language

Implement a small deterministic guard before the existing inference logic.

Recognize local negation/future patterns around start/completion phrases, including at minimum:

```text
not complete
not completed
not finished
not started
has not started
have not started
is not complete
is not completed
is not finished
isn't complete
isn't completed
isn't finished
hasn't started
haven't started
yet to complete
yet to be completed
yet to finish
pending completion
pending start
will complete
will be completed
will finish
will be finished
will start
scheduled to start
planned to start
expected to start
expected to be completed
to be completed tomorrow
to start tomorrow
```

The implementation may be more robust than this list, but must not become a giant brittle rule set.

### B. Suppress false inference

When negation/future context applies:

```python
progress = None
actual_start inference = None
actual_finish inference = None
```

unless the same sentence contains an independent explicit positive completed/start signal that clearly overrides the negation/future phrase.

### C. Route safely

Such reports must enter the existing safe review/422 pathway rather than creating a false completion/start update.

Do NOT solve this by inventing a fake progress value.

### D. Preserve evidence

The extracted event should still retain the original report text/evidence so the planner can understand why the system did not infer progress.

## Required regression tests

Add focused tests for at least:

```text
Spool XX102 at rack 3 not completed yet.
Spool XX103 at rack 3 will be completed tomorrow.
Spool XX104 at rack 3 not started due to rain.
Spool XX105 has not started.
Spool XX106 is not finished.
Spool XX107 yet to complete.
Spool XX108 completion is pending.
Spool XX109 will start tomorrow.
```

Assertions:

- no false `100%`
- no false actual start
- no false actual finish
- no unsafe AUTO confirmation
- safe review/422 behavior remains intact
- original evidence remains available

Also test positive controls so the fix does NOT break:

```text
Spool XX110 completed at rack 3.
Spool XX111 finished at rack 3.
Spool XX112 started at rack 3.
Spool XX113 installed, 100%.
```

These should continue to behave as the validated implementation expects.

---

# 3. MUST-FIX #2 — F-02 + F-13: Prevent progress regression and inconsistent completion state

## Problem

A completed activity can currently be changed from:

```text
100% / complete / actual_finish = date
```

to something like:

```text
30% / in_progress / actual_finish = same date
```

That creates contradictory schedule state.

Completed activities also need to be handled carefully by candidate selection.

## Required policy

### A. Default monotonic-progress rule

For a normal confirmed field-progress update:

```text
new_progress < current_progress
```

must NOT silently overwrite the activity.

At minimum, return a clear conflict/validation response and require an explicit planner override path.

### B. Completed activities

If the activity is:

```text
status = complete
AND/OR
progress = 100
AND/OR
actual_finish is set
```

then a later report with lower progress must NOT automatically reopen it.

Preferred behavior for this SIH build:

```text
422 / conflict
"Activity is already complete; lower progress requires explicit planner override."
```

Do not silently mutate the schedule.

### C. Preserve state consistency

Under the default path:

- `100%` → stays `100%`
- `complete` → stays `complete`
- `actual_finish` remains valid
- no new `in_progress` state is produced

If an explicit override/reopen mechanism already exists, preserve it. If not, do not build a large new workflow; a safe conflict response is sufficient for the SIH evaluation build.

### D. Candidate ranking

Completed activities should be down-ranked or flagged when a report appears to describe fresh work, so the matcher is less likely to propose a completed activity when an active candidate exists.

Do NOT change global thresholds solely to accomplish this.

## Required regression tests

Test:

1. `100% complete` + incoming `30% working`
   - no silent write
   - activity remains internally consistent

2. `70%` + incoming `30%`
   - no silent decrease

3. `30%` + incoming `70%`
   - normal positive update still works

4. `100% complete` + incoming `100%`
   - idempotent/safe behavior

5. completed candidate versus active candidate
   - active candidate is preferred where the existing scoring/context supports it

6. concurrent confirm behavior
   - preserve the existing one-approval-only behavior

---

# 4. MUST-FIX #3 — F-03: Pending AUTO_MATCHED events must remain reachable

## Problem

An AUTO_MATCHED event awaiting confirmation can disappear from the Review queue if the user leaves the ingest screen or abandons a Time Agent confirmation.

That means a system-generated pending decision can become unreachable.

## Required behavior

Every event that has:

```text
AUTO_MATCHED
AND
not yet approved/rejected
```

must be visible to the planner somewhere persistent in the UI.

Preferred implementation:

### Review Queue

Add an **"Awaiting confirmation"** section containing pending AUTO_MATCHED events.

Each item should show at least:

- event/report identifier
- project
- report excerpt
- proposed activity
- confidence/score
- evidence
- current status
- confirm action
- reject/review action

Do not allow a second approval.

Do not duplicate audit writes.

Do not turn AUTO_MATCHED into an automatic schedule write.

### Time Agent

If the Time Agent reaches:

```text
Confirm?
```

and the session is abandoned, the underlying pending event must still be discoverable through the normal planner workflow.

## Regression tests

Verify:

1. AUTO_MATCHED event created.
2. Leave ingest UI.
3. Open Review.
4. Event is visible in Awaiting Confirmation.
5. Confirm once.
6. Event disappears from pending list.
7. A second confirm returns the existing terminal-state error.
8. Exactly one schedule update and one audit record exist.

---

# 5. MUST-FIX #4 — F-04: Improve identifier extraction

## Problem

The current identifier extraction partially handles code-prefixed IDs but can miss common field references such as:

```text
P-301
P-302
P 305
V-201
Line 2104
Ln 2111
L-2104
```

This is especially important because identifiers are strong evidence for activity matching.

The current system safely routes several such cases to review, but the useful identifier evidence is being lost.

## Required behavior

Extend ID extraction to support:

### Equipment/tag forms

```regex
[A-Z]-?\d{3,4}
```

Examples:

```text
P-301
P301
P 301
V-201
T-101
```

### Bare line-number forms

When preceded by a line context token:

```text
line 2104
Line No. 2104
Ln 2111
L-2104
```

capture:

```text
2104
2111
```

### Important safety rule

Do NOT treat every random number as an identifier.

A bare number should require:

- recognized line context, OR
- a strong activity-code/description relationship

to become ID evidence.

## Matching behavior

Match extracted identifiers against:

- activity code
- activity description
- relevant structured schedule fields/tokens

Preserve the current scoring fusion.

Do not replace the current ID + lexical/fuzzy + semantic + context architecture with a new matcher.

## Required tests

Add cases for:

```text
Install pump P-301, 50%.
Erect vessel V-201, 60%.
Line 2104 piping segment erected at R01, 100%.
Ln 2111 spool installed at Rack 3.
L-2104 hydrotest started.
P303 installed.
PT-101 tested.
```

Check:

- useful ID evidence is produced where appropriate
- correct candidates receive evidence
- no cross-project leakage
- ambiguous cases remain REVIEW_REQUIRED rather than becoming unsafe AUTO_MATCHED

Run the dev benchmark first, then the frozen held-out benchmark exactly as-is.

---

# 6. SHOULD-FIX #5 — F-05: Prevent stale CPM/at-risk data

After the four safety fixes above, address forecast staleness with the smallest safe change.

## Required behavior

CPM/forecast/at-risk information should be recomputed when:

1. the application starts, and/or
2. the data date has changed since the last snapshot, and/or
3. an actual schedule write occurs

A GET of schedule intelligence should not continue displaying yesterday's forecast indefinitely after the date changes.

Do not replace the deterministic CPM implementation.

Add a focused regression test for:

```text
data date changes
→ GET schedule intelligence
→ forecast/at-risk snapshot refreshes
```

---

# 7. Small final-demo hardening

Apply these only after the MUST-FIX items pass and only if they can be implemented without destabilizing the validated flows.

## F-08 — Future report dates

Prevent obviously invalid future `report_date` values from being used as actual start/finish dates.

For example:

```text
report_date > today
```

should be rejected or safely routed to review.

Do not rewrite normal historical/current-date behavior.

## F-09 — Mobile layout

Fix the known 390×844 layout overflow and ensure:

- project selector remains usable
- action buttons remain accessible
- tables/cards do not break the page width

Do not redesign the desktop UI.

## F-10 — Time Agent session/project isolation

Ensure switching projects does not expose old conversation state from another project.

Do not redesign the agent.

## F-11 — Short-code candidate selection

Replace unsafe substring-style matching for short identifiers with exact/token-aware matching.

Add a regression test showing that a short code cannot accidentally match unrelated text.

## F-15 — Demo database hygiene

Do NOT modify production/shared data as part of development.

For the final evaluator package:

```powershell
python scripts/reset_demo_db.py
```

Then seed the intended demo state.

Make sure the committed repository does not depend on accidental local audit rows/reports from development.

---

# 8. Explicitly DO NOT change

Do not spend this hardening pass on unrelated architecture changes.

### Do not:

- migrate SQLite → PostgreSQL
- add Supabase
- add authentication/SSO for this prototype unless explicitly required by the deployment environment
- add XER support
- add 3D/BIM
- add mobile-native apps
- replace the matcher
- replace MiniLM with a different embedding model
- redesign CPM
- replace deterministic schedule logic with an LLM
- enable the unsafe reranker
- loosen AUTO_MATCHED thresholds
- manufacture benchmark improvements
- alter frozen benchmark labels
- remove difficult benchmark cases
- disable safety checks to make demos look smoother
- make AUTO_MATCHED equal to automatically written
- silently approve UNMATCHED
- remove audit records
- hide REVIEW_REQUIRED outcomes
- hard-code demo answers into the application

The project should remain explainable and defensible.

---

# 9. Testing protocol

Run these in order.

## 9.1 Backend tests

```powershell
python -m pytest -q
```

Required:

```text
ALL TESTS PASS
```

Do not accept a reduced test count as success.

## 9.2 Development benchmark

```powershell
python scripts/run_benchmark.py --split dev
```

Review:

- auto precision
- silent errors
- top-1
- recall@5
- decision distribution

Do not chase score increases at the expense of safety.

## 9.3 Frozen held-out benchmark

```powershell
python scripts/run_benchmark.py
```

The frozen benchmark must remain unchanged.

Record the new result.

Critical safety properties:

```text
0 silent errors
0 cross-project candidates
unknown cases continue to route safely
```

AUTO precision should not be traded for unsafe auto-matches.

## 9.4 Reranker

Do NOT use:

```powershell
python scripts/run_benchmark.py --reranker
```

for the evaluator-facing configuration.

Keep:

```text
PROGRESSSYNC_USE_RERANKER = disabled/off
```

unless a future validated benchmark proves it safe.

## 9.5 Frontend

```powershell
cd frontend-react
npm ci
npm run build
npm audit
cd ..
```

Required:

```text
build succeeds
npm audit = 0 vulnerabilities
```

## 9.6 Final clean DB

Create a fresh temporary/demo DB.

Do not use a contaminated development DB for the final evaluator demo.

Example:

```powershell
$env:PROGRESSSYNC_DB="$env:TEMP\progresssync_sih_final.db"
python scripts/reset_demo_db.py
```

Use the project's existing documented seed/bootstrap command afterward.

---

# 10. Final browser smoke test

Run the built application against a clean database.

Verify these exact scenarios.

## A — Confident report

Input a known confident field report.

Expected:

```text
AUTO_MATCHED
→ evidence shown
→ proposed activity shown
→ human confirmation required
→ schedule updates
→ audit row created
→ CPM reflects update
```

## B — Ambiguous report

Expected:

```text
REVIEW_REQUIRED
→ multiple candidates available
→ planner can choose/reassign
→ schedule changes only after confirmation
→ audit records decision
```

## C — Unknown activity

Expected:

```text
UNMATCHED
→ observation preserved
→ no fabricated activity_id
→ no schedule write
```

## D — Time Agent

Expected:

```text
field statement
→ clarification when required
→ same matching pipeline
→ proposed activity/evidence
→ human confirmation
→ schedule/audit update
```

## E — Schedule intelligence

Expected:

```text
actual update
→ Gantt
→ dependency/CPM recalculation
→ forecast/float/at-risk update
→ analytics
→ delay cause
→ institutional memory
```

---

# 11. Mandatory negative safety tests

Before final deployment, manually or automatically test these exact sentences:

```text
Piping crew: spool XX103 at rack 3 not completed yet.

Spool XX104 at rack 3 will be completed tomorrow.

Spool XX105 at rack 3 not started due to rain.

Spool XX106 has not started.

Spool XX107 is not finished.

Spool XX108 yet to complete.

Spool XX109 completion is pending.

Spool XX110 will start tomorrow.

Completed activity XX111 is now reported at 30%.
```

Expected:

- no false 100%
- no false actual start
- no false actual finish
- no silent progress regression
- no internally inconsistent completion state
- safe review/conflict behavior
- pending events remain reachable
- evidence is preserved

---

# 12. Mandatory positive safety tests

Also verify that legitimate field statements still work:

```text
Spool XX120 completed at rack 3.

Spool XX121 finished at rack 3.

Spool XX122 started at rack 3.

Spool XX123 installed, 40%.

Spool XX124 installed, 100%.
```

Expected existing behavior should remain intact.

---

# 13. Final repository hygiene

Before submission:

### Git status

```powershell
git status
git diff
git status --short
```

There must be no accidental generated files, local databases, caches, secrets, or temporary artifacts.

Review the final diff and ensure the final change set contains only intentional project work.

### No secrets

Check for:

- API keys
- tokens
- `.env` secrets
- local credentials
- private certificates
- personal machine paths that break deployment

### Documentation

Ensure these remain accurate:

- README
- demo/start instructions
- architecture documentation
- benchmark instructions
- environment/setup instructions
- limitations
- reranker warning
- final SIH demo instructions

Do not claim production accuracy from the synthetic benchmark.

---

# 14. Final commit

Only after the full test/smoke-test sequence passes:

```powershell
git add .
git status
git diff --cached
git commit -m "chore: final SIH evaluation hardening"
git status
```

Then record the exact commit SHA used for the evaluator build.

The deployment must use that exact commit, not an uncommitted working tree.

---

# 15. Final evaluator deployment checklist

### Core matching
- [ ] Schedule import works
- [ ] L5/L6 catalogue works
- [ ] dependency graph works
- [ ] lexical/fuzzy/context/semantic scoring works
- [ ] MiniLM works from the documented environment
- [ ] reranker disabled
- [ ] project isolation verified

### Safety
- [ ] no negation false-completion
- [ ] no future-tense false-completion/start
- [ ] no silent progress regression
- [ ] completed activities remain internally consistent
- [ ] UNMATCHED cannot be silently approved
- [ ] REVIEW_REQUIRED requires planner action
- [ ] AUTO_MATCHED still requires human confirmation
- [ ] pending AUTO_MATCHED events remain reachable
- [ ] one approval per event
- [ ] audit old/new values match actual schedule writes

### Schedule intelligence
- [ ] actual start/end/progress update correctly
- [ ] deterministic CPM recalculates
- [ ] critical path/float respond to actuals
- [ ] Gantt renders
- [ ] forecast/at-risk is not stale
- [ ] analytics works
- [ ] delay causes work
- [ ] institutional memory works

### Demo
- [ ] scenario A passes
- [ ] scenario B passes
- [ ] scenario C passes
- [ ] scenario D passes
- [ ] scenario E passes
- [ ] clean demo DB
- [ ] desktop UI works
- [ ] 390×844 layout no longer breaks
- [ ] browser console has no unexpected errors
- [ ] no accidental local data displayed

### Release
- [ ] `pytest` passes
- [ ] dev benchmark reviewed
- [ ] frozen benchmark passes
- [ ] `npm run build` passes
- [ ] `npm audit` = 0 vulnerabilities
- [ ] repository clean
- [ ] exact commit SHA recorded
- [ ] evaluator deployment uses exact final commit

---

# 16. Definition of Done

The implementation is **FINAL SIH EVALUATION READY** only when all of the following are true:

1. F-01 is fixed and covered by regression tests.
2. F-02/F-13 are fixed and covered by regression tests.
3. F-03 is fixed and the pending AUTO workflow is reachable.
4. F-04 is fixed and identifier extraction is validated.
5. F-05 is fixed or demonstrably guaranteed not to become stale during the evaluation flow.
6. Full backend tests pass.
7. Frozen benchmark passes without altering benchmark data or thresholds.
8. Reranker remains disabled.
9. Frontend builds cleanly.
10. The five A–E SIH scenarios pass again on a clean DB.
11. Negative safety cases pass.
12. Final repository is clean and committed.
13. The evaluator build uses the exact recorded commit.

---

# 17. Final instruction to Claude Code

Work directly in the existing repository.

Start by inspecting the current implementation and the existing tests.

Implement the fixes in this order:

```text
F-01 → F-02/F-13 → F-03 → F-04 → F-05 → small hardening items
```

After each major fix:

1. add/update regression tests,
2. run the focused tests,
3. run the full suite,
4. inspect the diff,
5. ensure no previously validated behavior was broken.

At the end, run the complete release protocol in this document.

Do not stop at “tests pass.” The goal is **safe, evaluator-facing behavior** under both positive and adversarial field-report wording.

Do not introduce new architecture unless it is necessary to satisfy a finding.

Do not optimize benchmark numbers by weakening safety.

When finished, produce a concise final implementation report containing:

```text
1. Files changed
2. F-01 status
3. F-02/F-13 status
4. F-03 status
5. F-04 status
6. F-05 status
7. Test count/result
8. Frozen benchmark result
9. Frontend build result
10. npm audit result
11. A–E browser smoke-test result
12. Final git commit SHA
13. Remaining known limitations, if any
14. FINAL SIH EVALUATION READY: YES/NO
```

If any mandatory item fails, report `NO` and identify the exact blocker instead of hiding or bypassing it.
