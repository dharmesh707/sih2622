# ProgressSync AI — Final Branch Reconciliation & Main Release Instruction

**Repository:** `https://github.com/dharmesh707/sih2622.git`  
**Project:** ProgressSync AI — SIH26122  
**Purpose:** Reconcile the current Git branches, preserve the validated SIH hardening and later deployment work, and publish one clean final code line to `main`.

---

## 0. Mission

Finalize the GitHub repository so that **`main` becomes the single canonical SIH evaluation branch**.

The repository currently has two relevant lines:

- `main`
- `sih-final-hardening`

The GitHub repository currently shows the branches as **diverged** rather than one being a simple fast-forward of the other.

Important known commits:

### Validated SIH hardening reference

```text
5c47051b63a08b206ed030dce1f155886bafc733
chore: final SIH evaluation hardening
```

This commit is the validated reference for the F-01 through F-15 hardening work.

### Current main tip

```text
ccefc18790253e19e574c4db5d5c8df09f825765
merge: finalize ProgressSync AI for SIH deployment
```

`main` also contains later deployment-oriented commits after the hardening reference, including Elastic Beanstalk ignore rules, Docker CPU-build optimization, demo deployment hardening, and the final implementation report.

### Critical instruction

**Do NOT simply reset `main` to `5c47051`.**

The task is to reconcile the branch differences and preserve the valid work from both lines.

---

# 1. Non-negotiable safety rules

1. Do not force-push.
2. Do not rewrite published history.
3. Do not delete the `sih-final-hardening` branch until the final `main` has been independently verified.
4. Do not weaken:
   - matching weights,
   - decision thresholds,
   - human confirmation before schedule writes,
   - negation protection,
   - progress-regression protection,
   - project isolation,
   - auditability.
5. Do not enable the reranker.
6. Do not modify the frozen benchmark to improve numbers.
7. Do not lower thresholds to increase AUTO_MATCHED volume.
8. Do not silently remove existing features to resolve a merge conflict.
9. Do not commit secrets, credentials, local databases, model caches, `node_modules`, Python caches, or temporary artifacts.
10. If a merge conflict affects behavior rather than documentation, inspect and test the affected feature before choosing a side.

---

# 2. Protected validated ProgressSync core

The following functionality is already implemented and must survive branch reconciliation.

## Ingestion

- CSV schedule import
- XLSX schedule import
- schedule activity retrieval
- field report ingestion
- spreadsheet/report ingestion paths already present
- Time Agent input
- report persistence

## Event extraction

- identifiers
- equipment/line tags
- line-number references
- discipline
- location
- quantity
- progress
- time/date
- source evidence span
- inference reason/note
- negation/future-tense guard

## Matching

Preserve the existing retrieve-then-rank architecture:

```text
candidate retrieval
→ identifier evidence
→ lexical/fuzzy evidence
→ MiniLM semantic evidence
→ context evidence
→ score fusion
→ candidate ranking
→ margin
→ AUTO_MATCHED / REVIEW_REQUIRED / UNMATCHED
```

Do not redesign the matching engine during branch reconciliation.

## Decision and safety

- AUTO_MATCHED
- REVIEW_REQUIRED
- UNMATCHED
- human confirmation before schedule writes
- candidate comparison
- reassign
- reject
- explicit manual association only
- Awaiting confirmation for pending AUTO_MATCHED
- exactly one approval per event
- approved/rejected are terminal
- concurrent confirmation safety
- no one-click fabricated approval for UNMATCHED

## Update logic

- actual start
- actual finish
- percentage complete
- monotonic progress
- no silent reopening of completed activities
- audit entry
- optional delay cause
- execution memory update
- CPM recompute

## Schedule intelligence

- activity catalogue
- WBS context
- dependency graph
- CPM
- critical path
- float
- forecast finish
- downstream at-risk logic
- schedule snapshot/diff
- data-date freshness
- Gantt

## Analytics and memory

- planned-vs-actual / variance views
- discipline analytics
- delay causes
- institutional memory

## Auditability

- report/event evidence
- scores and margins
- decision path
- actor
- timestamp
- previous state
- new state
- approval status

## Project isolation

All matching, confirmation, audit, analytics, memory and review behavior must remain project-scoped.

## Validated ML state

- MiniLM semantic model remains the semantic model
- model revision remains pinned as documented
- reranker remains disabled by default
- semantic matching must remain explainable through evidence/score components

---

# 3. First step — inspect before changing

Run from a clean clone/worktree:

```powershell
git fetch --all --prune
git status
git branch -a
git branch -vv
git log --oneline --graph --decorate --all -40
```

Then inspect:

```powershell
git show --stat 5c47051b63a08b206ed030dce1f155886bafc733
git show --stat ccefc18790253e19e574c4db5d5c8df09f825765
```

Compare:

```powershell
git diff main...sih-final-hardening
git diff sih-final-hardening...main
git log --left-right --oneline main...sih-final-hardening
```

Before editing, write a short table:

| Difference | Origin branch | Action |
|---|---|---|
| SIH safety hardening | `sih-final-hardening` | Preserve |
| Deployment improvements | `main` | Preserve |
| Documentation-only differences | either | Reconcile |
| Duplicate/obsolete docs | either | Normalize |
| Conflicting code | both | Resolve + test |

Do not start by force-resetting either branch.

---

# 4. Integration strategy

Use the following target structure:

```text
validated hardening reference
        +
later main deployment improvements
        ↓
integrated working tree
        ↓
full tests + benchmark + browser smoke test
        ↓
new final commit
        ↓
push to origin/main
```

The final `main` must contain the **union of the valid work**, not an arbitrary branch winner.

### Preferred approach

Create a temporary integration branch from the current `main`:

```powershell
git checkout main
git pull --ff-only
git checkout -b final-main-integration
```

Then bring in the validated hardening changes from `sih-final-hardening`.

Preferred first attempt:

```powershell
git merge --no-ff origin/sih-final-hardening
```

If conflicts occur, resolve them carefully.

Do NOT use blanket merge strategies such as:

```powershell
git merge -X theirs ...
git merge -X ours ...
```

The code must be reconciled by feature, not by branch preference.

---

# 5. Conflict-resolution rules

If a conflict affects backend safety logic, protect the validated hardening behavior from `5c47051`.

### F-01

Negated/future wording must not infer:

- 100%
- start
- finish

Examples:

```text
not completed yet
not started
will be completed tomorrow
will start tomorrow
completion is pending
yet to complete
```

must not create unsafe schedule updates.

### F-02 / F-13

Progress must remain monotonic.

A completed activity must not silently become:

```text
30%
in_progress
```

while keeping an invalid `actual_finish`.

Lower progress must be rejected safely.

### F-03

Pending AUTO_MATCHED decisions must remain reachable via:

```text
Awaiting confirmation
```

### F-04

Preserve improved identifiers:

```text
P-301
P301
P 301
V-201
T-101
P303
PT-101
Line 2104
Ln 2111
L-2104
Line No. 2104
```

A random number must not become identifier evidence without appropriate context.

### F-05

CPM/forecast/at-risk must refresh when the data date changes.

---

# 6. Main branch deployment work must also be preserved

The later `main` line contains deployment-related work.

Inspect and preserve compatible changes involving:

- Elastic Beanstalk ignore configuration
- Docker CPU/PyTorch build optimization
- demo deployment hardening
- final deployment documentation
- authentication/token configuration already present
- single-container FastAPI + React deployment
- pinned semantic-model provisioning

These are part of the deployment story and should not be lost merely because the SIH hardening branch is older.

---

# 7. Normalize repository documentation

After integration, inspect:

```powershell
Get-ChildItem -Recurse docs
```

Prefer these canonical locations:

```text
docs/
  architecture.md
  api.md
  demo.md
  testing.md
  reports/
    ProgressSync_AI_Final_Audit.md
    ProgressSync_AI_Final_Implementation_Report.md
  prompts/
    ProgressSync_Remediation_Audit_v1.md
```

Avoid accidental duplicate filenames such as:

```text
ProgressSync_Remediation_Audit_v1 (1).md
```

Do not delete useful historical records without checking references first.

Normalize README and internal links to the canonical paths.

---

# 8. Ensure the remediation instruction is in GitHub

The final repository should contain:

```text
docs/prompts/ProgressSync_Remediation_Audit_v1.md
```

This document is an implementation instruction for future remediation work.

It must clearly distinguish:

```text
implemented
verified
planned / roadmap
```

Do not present proposed WhatsApp, React Native, dynamic multi-plant onboarding, or audit export work as implemented unless acceptance criteria were actually demonstrated.

---

# 9. Verify README claims

Ensure README accurately describes the actual final code, including:

- CSV/XLSX schedule import
- dependencies
- event extraction
- identifier forms
- negation/future handling
- project-scoped matching
- MiniLM semantic matching
- AUTO/REVIEW/UNMATCHED
- human confirmation
- Awaiting confirmation
- progress protection
- CPM
- Gantt
- analytics
- delay causes
- institutional memory
- Time Agent
- benchmark limitations
- reranker disabled
- current deployment instructions

Do not claim unsupported future features as implemented.

---

# 10. Run the complete test suite after reconciliation

```powershell
python -m pytest -q
```

Required:

```text
0 failures
```

The known-good hardening reference had:

```text
160 passed
```

A different final count is acceptable only if the added tests are intentional and all tests pass.

Do not remove tests to return to an old number.

---

# 11. Frozen benchmark

Run:

```powershell
python scripts/run_benchmark.py
```

Required safety properties:

```text
0 silent errors
0 cross-project candidates
unknown cases remain safely unmatched
no unexplained reduction in auto precision
```

Reference hardening result:

```text
AUTO precision: 100%
Silent errors: 0
Top-1: 76.2%
R@5: 92.1%
Unknown → UNMATCHED: 13/13
Cross-project: 0
```

Do not modify frozen benchmark data, labels, manifest, or matching thresholds.

---

# 12. Frontend validation

```powershell
cd frontend-react
npm ci
npm run build
npm audit
cd ..
```

Required:

- build succeeds
- no high/critical vulnerabilities
- no unexplained dependency churn

---

# 13. Clean demo database

Use a fresh demo database:

```powershell
$env:PROGRESSSYNC_DB="$env:TEMP\progresssync_final_main.db"
python scripts/reset_demo_db.py
```

Do not commit the database.

---

# 14. Browser smoke test

Start:

```powershell
uvicorn backend.app:app --port 8000
```

Verify:

### A — confident

```text
report
→ AUTO_MATCHED
→ evidence
→ human confirmation
→ schedule update
→ audit
→ CPM
```

### B — ambiguous

```text
report
→ REVIEW_REQUIRED
→ candidate comparison
→ planner selection/reassignment
→ schedule update
→ audit
```

### C — unknown

```text
unknown activity
→ UNMATCHED
→ observation preserved
→ no fabricated activity
→ no unsafe one-click approval
```

### D — Time Agent

```text
statement
→ clarification
→ same event continuation
→ confirmation
→ schedule/audit update
```

### E — schedule intelligence

```text
actual update
→ Gantt
→ CPM/critical path
→ float/forecast
→ at-risk
→ analytics
→ delay cause
→ institutional memory
```

---

# 15. Mandatory negative tests

Run these exact cases:

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

Required:

- no false 100%
- no false actual start
- no false actual finish
- no silent regression
- no inconsistent completed activity
- no unsafe confirm

---

# 16. Mandatory positive tests

Verify:

```text
Spool XX120 completed at rack 3.
Spool XX121 finished at rack 3.
Spool XX122 started at rack 3.
Spool XX123 installed, 40%.
Spool XX124 installed, 100%.
```

Do not break positive extraction while preserving the negative guard.

---

# 17. Deployment configuration check

Inspect:

```powershell
Get-Content Dockerfile
Get-Content requirements.txt
Get-Content .env.example
```

Confirm:

- semantic model revision is pinned
- model provisioning is documented
- runtime model loading works offline after provisioning
- reranker stays off
- API token behavior matches README
- CORS settings match deployment documentation
- no credentials are hardcoded

---

# 18. Secrets and generated-file audit

Before committing:

```powershell
git status --short
git diff
```

Do not commit:

- `.env`
- bearer tokens
- AWS credentials
- Twilio credentials
- API keys
- private keys
- SQLite databases
- `node_modules`
- `dist`
- `.pytest_cache`
- `__pycache__`
- temporary benchmark outputs
- local model caches
- machine-specific files

Review `.gitignore`.

---

# 19. Commit the reconciled final code

Only after all validation passes:

```powershell
git status
git diff
git add <specific-files>
git commit -m "chore: finalize ProgressSync AI for SIH evaluation"
git diff HEAD^ HEAD --stat
git status
```

Do not blindly use `git add .`.

Review staged changes before commit.

---

# 20. Push the final integration

Push the integration branch first:

```powershell
git push -u origin final-main-integration
```

Verify the remote branch.

Then merge into `main` through the normal repository flow.

Preferred:

```text
final-main-integration
        ↓
Pull Request
        ↓
main
```

Do not force-push `main`.

If direct push is specifically required and the branch is fast-forwardable:

```powershell
git checkout main
git pull --ff-only
git merge --ff-only final-main-integration
git push origin main
```

If it is not fast-forwardable, stop and resolve normally rather than forcing.

---

# 21. Verify GitHub state

After push:

```powershell
git fetch origin
git rev-parse HEAD
git rev-parse origin/main
git status
```

Expected:

```text
local HEAD == origin/main
working tree clean
```

Verify on GitHub that `main` contains the intended final source and documentation.

---

# 22. Preserve rollback reference

Keep:

```text
sih-final-hardening
```

until the final deployment has been verified.

Rollback reference:

```text
5c47051b63a08b206ed030dce1f155886bafc733
```

Do not delete the branch before evaluator deployment is confirmed.

---

# 23. Final GitHub state

The target state is:

```text
origin/main
    ↓
one canonical final SIH code line
    ↓
validated hardening
+
later deployment improvements
+
tests passing
+
benchmark passing
+
documentation aligned
+
no secrets
+
clean repository
+
reproducible deployment
```

The evaluator build must use the exact GitHub commit on `main`.

Never deploy from an uncommitted working tree.

---

# 24. Final report to the team

Return exactly:

```text
Repository:
Final branch:
Final main commit SHA:
Previous hardening reference:
Branches inspected:
Conflicts found:
Conflicts resolved:
Tests:
Frozen benchmark:
Frontend build:
NPM audit:
Scenario A:
Scenario B:
Scenario C:
Scenario D:
Scenario E:
Negative safety tests:
Reranker:
Documentation status:
Secrets check:
Working tree:
origin/main sync:
Evaluator deployment commit:
Remaining limitations:
FINAL SIH EVALUATION READY: YES / NO
```

If any safety-critical validation fails:

```text
FINAL SIH EVALUATION READY: NO
```

Do not hide the failure.

---

# 25. Final instruction

The objective is **one final `main` branch**, not a blind branch replacement.

The final `main` must preserve:

- the validated ProgressSync core,
- the validated F-01…F-15 hardening,
- the later deployment improvements already present on `main`,
- passing tests,
- the frozen benchmark,
- accurate documentation,
- and a clean reproducible Git commit.

Final state:

```text
verified
committed
pushed
clean
rollback-capable
evaluator-ready
```
