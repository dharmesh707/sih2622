# ProgressSync AI (SIH26122): Final SIH Evaluation Hardening, Implementation Report

| | |
|---|---|
| **Project** | ProgressSync AI, SIH26122 (Oil India Limited) |
| **Task** | Final SIH evaluation hardening pass |
| **Plan executed** | [docs/prompts/ProgressSync_AI_Final_SIH_Evaluation_Ready_Hardening_Prompt.md](docs/prompts/ProgressSync_AI_Final_SIH_Evaluation_Ready_Hardening_Prompt.md) (all 17 sections) |
| **Findings source** | [docs/reports/ProgressSync_AI_Final_Audit.md](docs/reports/ProgressSync_AI_Final_Audit.md) (final audit, 2026-09-26) |
| **Date** | 2026-09-26 |
| **Final commit** | **`5c47051`** (`5c47051b63a08b206ed030dce1f155886bafc733`), message `chore: final SIH evaluation hardening` |
| **Branch** | `sih-final-hardening` (created from `main` @ `3b1ffc7`; `main` itself was not changed) |
| **Pushed / merged** | No. The commit exists only in the local repository |
| **Environment** | Windows 11; Python 3.13.5 in a venv at `%TEMP%\psv` built from the pinned `requirements.txt`; Node v24.19.0; MiniLM `sentence-transformers/all-MiniLM-L6-v2@1110a243fdf4706b3f48f1d95db1a4f5529b4d41` from the local Hugging Face cache |
| **Implemented and verified by** | Claude Code (Claude Opus 5.5) in a single session. The same agent implemented and verified the work, so there was no independent human review. |

---

## 1. Summary

The audited repository was demo-ready but had two high-severity data-integrity defects (F-01, F-02), one workflow reachability defect (F-03) and one extraction gap (F-04). All were fixed in the prescribed order, followed by F-05 and the small hardening items (F-08, F-09, F-10, F-11, F-15).

Every fix has regression tests. The full release protocol ran on the final code, and the final commit was built, tested and exercised again from a clean checkout of that exact commit.

Before any change, the existing uncommitted work was snapshotted outside the repository: a 194,410-byte tracked diff plus a 27-file untracked archive, both in the session scratchpad. After the work, every snapshot file was confirmed still present. The only absent paths are the 4 deletions that the earlier phase had already staged on purpose: `frontend/app.js`, `frontend/index.html`, `frontend/styles.css`, and the root `package-lock.json`.

**Result: FINAL SIH EVALUATION READY: YES** (see §9 for the verification of each Definition of Done item, and §11 for limitations).

---

## 2. Fixes in the prescribed order

### F-01: negated and future-tense wording (MUST-FIX #1): ✅ Fixed

- **Problem:** "not completed yet", "will be completed tomorrow" and "not started" were read as 100% or as an actual start, AUTO_MATCHED, and one confirm click wrote a wrong schedule state.
- **Change** (`backend/app.py`):
  - A small deterministic guard, `NEGATED_OR_FUTURE`, blocks the completion/start verb it governs: `not`, `never`, `no`, `yet to`, `pending`, `will`, `shall`, `going to`, `to be`, `scheduled/planned/expected/about to`, `*n't`, and `… is pending/awaited/tomorrow/later`.
  - An unguarded positive verb in the same sentence still counts, e.g. "not started last week but completed today".
  - An explicit current % is kept ("not completed yet, 60%" → 60).
  - A contradictory "will be completed tomorrow, 100%" gives no progress.
  - `started_signal()` is shared by extraction, `apply_update` and the Time Agent.
  - `inference_note` preserves the reason; the original text is kept as evidence.
  - Routing: a confident match whose report has nothing to apply becomes `REVIEW_REQUIRED` with the reason "confident match … but the report states no progress or start to apply — its wording is negated or future tense". This is not a threshold change.
  - Confirming such an event returns **422** with an explanation, and nothing is written.
- **Tests:** `tests/test_negation.py`, 46 tests. They cover all required negative sentences from §2 and §11 plus other listed phrasings, all positive controls from §2 and §12, the never-AUTO and never-written path (422, unchanged activity, no audit row, still in the review queue), the downgrade reason, positive confirm paths, and the Time Agent. Focused run: **46 passed**. Full suite after F-01: **110 passed**.

### F-02 + F-13: progress regression and completed candidates (MUST-FIX #2): ✅ Fixed

- **Change** (`apply_update`, `make_match`):
  - Progress is monotonic.
    - A complete activity (status `complete`, or ≥100%, or `actual_finish` set) is not reopened by any report below 100% or by a start-only report. It returns **409** "… is already complete; lower progress requires explicit planner override. Nothing was written …".
    - Lower-than-current progress returns **409**. Validation runs before any write.
  - A repeat 100% is idempotent and keeps the first `actual_finish`.
  - There is no override workflow (per §3C, a conflict response is sufficient); the planner rejects the report.
  - Completed activities are flagged (`completed_activity`) and multiplied by `COMPLETED_ACTIVITY_FACTOR = 0.85` for fresh-work reports. The UI shows an "already complete" chip and "×0.85 done". Global thresholds are unchanged.
- **Defect found while testing, and fixed:** the concurrent-confirm test returned `[200, 409, 409, 500]`. The 500 was `IntegrityError: UNIQUE constraint failed: match_decisions.event_id`, a check-then-write race. The unique index already kept exactly one approval, so no data was corrupted. The fix maps that violation to 409. A stress repro gave `[200, 409, 409, 409]` in 6 of 6 trials, with 1 audit row per event.
- **Tests:** `tests/test_progress_policy.py`, 7 tests: complete + 30% (no write, consistent state, still rejectable), start report on a complete activity, 70% → 30%, 30% → 70%, complete + 100% idempotent, active-vs-completed twin, concurrent confirms. Three repeat runs: **7 passed** each. Full suite: **117 passed**.

### F-03: pending AUTO_MATCHED events reachable (MUST-FIX #3): ✅ Fixed

- **Change:**
  - New `GET /api/v1/awaiting-confirmation?project_id=`, listing latest-decision AUTO_MATCHED events with the proposed activity, scores, reason, report text, source and time.
  - New `POST /api/v1/events/{id}/send-to-review` (409 unless the event is pending AUTO).
  - Review queue UI: an **"Awaiting confirmation"** section with a top-3 candidate table and Confirm / Send to review / Reject. Confirm reuses the guarded path, so there is no second approval and no duplicate audit row.
- **Tests:** `tests/test_awaiting.py`, 4 tests: the full §4 sequence (created → listed → confirmed once → gone → second confirm 409 → exactly one audit row and one schedule update), send-to-review and reject, an abandoned Time Agent "Confirm?", and project scoping. **4 passed**. Full suite: **121 passed**. The React build succeeded.

### F-04: identifier extraction (MUST-FIX #4): ✅ Fixed

- **Change:**
  - `LINE_REF` captures numbers after `line`, `Ln`, `L-`, `Line No.`. A bare number never counts without that context.
  - `TAG_REF` adds single-letter tags (`P-301`, `P301`, `P 301`, `V-201`, `T-101`); a tag directly followed by `%` is never an identifier.
  - `id_in()` makes identifier-vs-code/description matching **whole-token** (it was substring matching).
  - The fusion architecture is unchanged.
- **Refinement from the dev benchmark:**
  - The first version gave line numbers 1.0 ID credit, which also triggers the lexical 0.9 / semantic 0.92 floors. On the **dev** split, top-1 dropped from 83.7% to **71.4%** (terminology 40%, exact 75%, missing_timestamp 75%), with 0 silent errors.
  - Cause: one line number is shared by several activities (erect, pressure test, bolting), and the floors flattened the wording that separates them.
  - Fix: line numbers are line-level evidence at **0.82**, with no floors; tags stay at 1.0.
  - Diagnosed on dev only; the held-out set was not used.
  - One earlier test assertion (`test_safety.py`, line number → 0.82) failed on the first version and passes again after the refinement; its comment was updated.
- **Extraction check:** `P-301`, `V-201`, `2104`, `2111`, `2104` (from `L-2104`), `P303`, `PT-101`, `P 305`, `2104` (from `Line No.`), and `T-101` are extracted. "Area A 100% complete", "Crew of 12 …", "Level 2104", and "Pull 2104 cables" give `[]`.
- **Tests:** `tests/test_identifiers.py`, 22 tests. They cover extraction forms, random numbers not being identifiers, and tag evidence reaching the right candidate when activity codes do **not** contain the digits. They also cover line-level evidence shared by the line's activities (0.82), a near-miss number (`line 210`) giving no evidence and not AUTO, and no cross-project leakage. Focused: **21 passed**, then **22** after adding the line-number test. Full suite: 1 failed / 141 passed on the first version, **143 passed** after the refinement.

### F-05: stale CPM / at-risk (SHOULD-FIX #5): ✅ Fixed

- **Change:**
  - `schedule_snapshots.data_date`, added by an additive migration and set by `recompute`.
  - `refresh_if_stale()` runs at startup for every project, and on `GET /projects/{id}/activities` and `/critical-path` when the latest snapshot's data date is not today.
  - A cyclic graph is skipped there; the explicit recompute still reports 409.
  - The CPM mathematics is unchanged.
- **Tests:** `tests/test_freshness.py`, 4 tests: same-day GET does not recompute; a data-date move of +10 days refreshes the snapshot, increases at-risk, adds late-start reasons and moves the forecast; the critical-path GET refreshes too; a legacy snapshot without a data date is refreshed. **4 passed**. Full suite: **147 passed**.

---

## 3. Other hardening items (§7)

| Item | Status | Change | Verification |
|---|---|---|---|
| F-08 future report dates | ✅ | `report_date > today` returns **422** (Pydantic validator); nothing is stored | `test_hardening.py` |
| F-09 mobile layout | ✅ | Project selector kept at ≤850 px (only the label, pulse and divider are hidden); `min-width:0` on content and grid children; `minmax(0,1fr)` grid columns; file input constrained; active nav label hidden in the narrow rail. The desktop design is unchanged | Browser at 390×844, all 5 views: `innerWidth/scrollWidth = 390/390`, selector visible, 0 off-screen buttons, with populated data |
| F-10 Time Agent project isolation | ✅ | A `session_id` from another project starts a new session instead of resetting or reusing the old one; `GET /agent/sessions/{id}?project_id=` returns 404 on mismatch; the UI passes `project_id` | `test_hardening.py` |
| F-11 short-code selection | ✅ | `code_named()`: whole-token, case-insensitive; `A1` does not match "Area 1" or "a1b" | `test_hardening.py` (7 parametrized cases + agent flow) |
| F-15 demo DB hygiene | ✅ | Local `data/progresssync.db` (gitignored) reset with `scripts/reset_demo_db.py`. Before: 4 audit rows, 5 reports, 1 delay cause, 1 agent session. After: 0 / 0 / 0 / 0 with 35 activities. No DB file is committed | read-only SQLite count before and after |

`tests/test_hardening.py` has 13 tests and ran as **13 passed** focused.

**Demo sample change** (found during the smoke test): the UI's "Load ambiguous example" now fills `Pump CT103 installed at Unit 2, 50%.` Five seeded pumps share tag CT-103, so it is a real tie that routes to REVIEW_REQUIRED (margin 0.000) regardless of demo order.

The previous spool sample fell to UNMATCHED (0.433 < 0.45) after scenario A had completed its former top candidate PIP-L5-002, because of the F-13 down-ranking. That is expected behaviour. Only the sample text changed; no matching logic or threshold changed. `docs/demo.md` explains this.

---

## 4. Changed files

**Final commit `5c47051`:** 61 files changed, 6,531 insertions and 606 deletions (30 added, 27 modified, 4 deleted). This includes the previously uncommitted next-phase work.

The hardening pass itself changed or added these files:

| Area | Files |
|---|---|
| Backend | `backend/app.py` (hardening-only diff: +147 / −33 lines, where the removals were the replaced old logic) |
| Frontend | `frontend-react/src/views/ReviewView.jsx`, `frontend-react/src/views/IngestView.jsx`, `frontend-react/src/components/TimeAgentPanel.jsx`, `frontend-react/src/components/CandidateList.jsx`, `frontend-react/src/components/Layout.jsx`, `frontend-react/src/styles.css` |
| New tests | `tests/test_negation.py`, `tests/test_progress_policy.py`, `tests/test_awaiting.py`, `tests/test_identifiers.py`, `tests/test_freshness.py`, `tests/test_hardening.py` |
| Updated test | `tests/test_safety.py` (one assertion comment) |
| Docs | `README.md`, `docs/api.md`, `docs/demo.md`, `docs/testing.md`, `docs/architecture.md`, `PROGRESS.md` |
| Config | `.gitignore` (adds `benchmark/v2/results/`, since per-case benchmark output is generated) |

These were **not changed**:
- frozen benchmark data (`benchmark/v2/*.csv`, `*.jsonl`, `MANIFEST.json`);
- matching thresholds (0.82 / 0.12 / 0.45);
- reranker default (off);
- the `one_approval_per_event` index.

---

## 5. Test results

| Point in the work | Command | Result |
|---|---|---|
| Baseline (final audit) | `python -m pytest -q` | 64 passed |
| After F-01 | full suite | 110 passed |
| After F-02/F-13 | full suite | 117 passed |
| After F-03 | full suite | 121 passed |
| F-04 first version | full suite | **1 failed**, 141 passed (`test_safety.py::test_code_prefix_inside_a_word_is_not_identifier_evidence`); fixed by the line-number refinement |
| After F-04 refinement | full suite | 143 passed |
| After F-05 | full suite | 147 passed |
| §9.1 final | `python -m pytest -q` | **160 passed, 1 warning** (Starlette TestClient re-export warning from inside FastAPI), 30.94 s |
| Before commit (re-run) | `python -m pytest -q` | **160 passed, 1 warning**, 31.07 s |
| Clean checkout of `5c47051` | `python -m pytest -q -p no:cacheprovider` | **160 passed, 1 warning**, 33.42 s |

New tests by file: `test_negation` 46, `test_progress_policy` 7, `test_awaiting` 4, `test_identifiers` 22, `test_freshness` 4, `test_hardening` 13. That is 96 new tests, and 64 + 96 = 160.

---

## 6. Benchmark results

Command: `python scripts/run_benchmark.py [--split dev]`. The runner verifies `benchmark/v2/MANIFEST.json` SHA-256 hashes before scoring; this is a synthetic corpus, **not production accuracy**.

### 6.1 Summary

| Run | Split | Auto precision (n auto) | Silent errors | AUTO / REVIEW / UNM | Top-1 | R@5 | Unknown → UNMATCHED | Cross-project | Median latency |
|---|---|---|---|---|---|---|---|---|---|
| Before hardening (audit) | dev (56) | 100% (15) | 0 | 26.8 / 69.6 / 3.6% | 83.7% | 98.0% | 1/1 | 0 | 43.8 ms |
| Before hardening (audit) | held-out (84) | 100% (13) | 0 | 15.5 / 67.9 / 16.7% | 76.2% | 92.1% | 13/13 | 0 | 61.7 ms |
| F-04 first version | dev | 100% (17) | 0 | 30.4 / 66.1 / 3.6% | **71.4%** | 98.0% | 1/1 | 0 | 91.9 ms |
| F-04 refined | dev | 100% (22) | 0 | 39.3 / 57.1 / 3.6% | 83.7% | 98.0% | 1/1 | 0 | 49.5 ms |
| After F-01 to F-05 + hardening | held-out | 100% (21) | 0 | 25.0 / 58.3 / 16.7% | 76.2% | 92.1% | 13/13 | 0 | 73.3 ms |
| **§9.2 final** | **dev** | **100% (22)** | **0** | 39.3 / 57.1 / 3.6% | **83.7%** | 98.0% | 1/1 | **0** | 50.4 ms |
| **§9.3 final** | **held-out** | **100% (21)** | **0** | 25.0 / 58.3 / 16.7% | **76.2%** | **92.1%** | **13/13** | **0** | 74.2 ms |
| Clean checkout of `5c47051` | held-out | 100% (21) | 0 | 25.0 / 58.3 / 16.7% | 76.2% | 92.1% | Not recorded (per-category table not printed in this run) | 0 | 82.9 ms |

### 6.2 Final held-out per-category (§9.3)

| Category | n | Top-1 | R@5 | AUTO | REVIEW | UNM | Silent |
|---|---|---|---|---|---|---|---|
| abbreviation | 11 | 72.7% | 100.0% | 0 | 11 | 0 | 0 |
| exact | 6 | 100.0% | 100.0% | 2 | 4 | 0 | 0 |
| granularity | 8 | n/a | n/a | 0 | 7 | 1 | 0 |
| missing_timestamp | 10 | 100.0% | 100.0% | 10 | 0 | 0 | 0 |
| near_duplicate | 9 | 0.0% | 44.4% | 0 | 9 | 0 | 0 |
| synonym | 4 | 75.0% | 100.0% | 1 | 3 | 0 | 0 |
| terminology | 9 | 100.0% | 100.0% | 3 | 6 | 0 | 0 |
| typo_ocr | 7 | 100.0% | 100.0% | 1 | 6 | 0 | 0 |
| unknown | 13 | n/a | n/a | 0 | 0 | 13 | 0 |
| wrong_discipline | 7 | 71.4% | 100.0% | 4 | 3 | 0 | 0 |

### 6.3 Reranker

The reranker was **not run and not enabled** in this session, per §9.4. `GET /api/v1/ml/status` on the served app reported `"reranker_enabled": false`.

Its last measurement (6 silent errors on held-out) comes from the 2026-09-26 audit, **before** the hardening changes. Reranker behaviour on the hardened code: **Not recorded**.

---

## 7. Frontend build and npm audit

| Run | Result |
|---|---|
| §9.5 (`rm -rf node_modules dist && npm ci && npm run build && npm audit`) | build OK (JS `index-DuWktINr.js` 261.38 kB / 79.96 kB gzip; CSS 13.62 kB / 3.68 kB gzip); **0 vulnerabilities** |
| §9.5 re-run after the last UI change (sample text), before commit | build OK ("built in 4.34s"; sizes not recorded); **0 vulnerabilities** |
| Clean checkout of `5c47051` (`npm ci && npm run build && npm audit`) | build OK ("built in 3.06s"); **0 vulnerabilities** |

Every `npm ci` printed an `allow-scripts` warning about esbuild's postinstall.

---

## 8. Clean database, browser smoke test and evaluator build

### 8.1 Clean database (§9.6)

`PROGRESSSYNC_DB=%TEMP%\progresssync_sih_final.db`, then `python scripts/reset_demo_db.py` → "35 seeded activities, 8 terminology mappings".

With the app served (`uvicorn backend.app:app --port 8000`):
- `/audit`, `/awaiting-confirmation` and `/review-queue` for project 1 returned `[]`.
- `/ml/status`: `semantic_model_available: true`, `reranker_enabled: false`.

### 8.2 Browser smoke test (§10–§12)

- **Tool:** Chrome DevTools MCP.
- **Target:** the built React UI served by FastAPI on the clean DB.
- **Method:** real clicks and form input, with results read from the DOM.

A first full run was **discarded** after the ambiguous-sample change (§3). The UI was rebuilt, the DB reset again, and the complete run below was repeated.

| Scenario | Outcome |
|---|---|
| **A: confident** | `Piping crew completed spool XX102 at rack 3, 100%.` → AUTO_MATCHED event #1, PIP-L5-002, top 0.965, runner-up 0.434, margin 0.531. Evidence row: ID 1.00, lexical 0.90, semantic 0.92, context 1.00, `spool → piping segment, rack 3 → R03`. **Confirm** was required ("Confirm update to PIP-L5-002") → 0% → 100%, not_started → complete, actual 2026-09-26/2026-09-26, audit #1 `approved`, CPM panel (forecast finish 2026-10-30 → 2026-10-30). **Pass** |
| **F-03 in UI** | `Piping crew completed spool XX104 at rack 3, 100%.` → AUTO_MATCHED event #2 (PIP-L5-016, 0.907, margin 0.455), left unconfirmed → Review showed "Awaiting confirmation · 1 confident match not yet confirmed" → Confirm PIP-L5-016 → the section disappeared; a second confirm returned **409**; audit rows for event #2: **1**. **Pass** |
| **B: ambiguous** | the ambiguous example → REVIEW_REQUIRED event #3, "margin 0.000 to runner-up below 0.12", top-3 ROT-L5-004, ROT-L5-011, ROT-L5-018 → in Review, selected rank 2 with a comment → "Reassign to ROT-L5-011" → `REASSIGNED`, 0% → 50%, not_started → in_progress. **Pass** |
| **C: unknown** | `ZZ-999 unknown activity at offshore platform, 20%.` → UNMATCHED event #4, "Observation preserved without a schedule link", "report explicitly names an unknown work package". In Review the action button read "Select an activity" and was **disabled**. **Pass** |
| **D: Time Agent** | `XX103 started at 9.` → "Where is this work? My best guess is PIP-L5-009 (Erect line XX103 spool 009) at R03 …" (REVIEW_REQUIRED, event #14) → `Rack 3.` → same event #14, AUTO_MATCHED, "score 0.879, margin 0.481 … Confirm? (yes / no)" → **Yes, record it** → "Recorded on PIP-L5-009: status not_started → in_progress … actual start 2026-09-26, audit #4". **Pass** |
| **E: schedule intelligence** | `Foundation concrete poured at Area A, 40%.` → Review → CIV-L5-008 with delay cause `weather` → 0% → 40%, forecast project finish **2026-10-30 → 2026-10-27 (−3.4d)**, downstream float PIP-L5-009 17.0d→13.6d and ROT-L5-011 28.5d→25.1d, at-risk list "None", audit #5. Gantt: 35 activities, 48 dependencies, 0 at risk (CIV-L5-008 "40% · 0.0d in_progress fcst 09-29"). Analytics: average start/finish/duration variance −4.5d / −6d / −2.33d, 3 completed / 6 started; delay causes weather ×1 (2026-W39). Memory: 6 rows. Audit trail: 5 rows. **Pass** |
| **§11 negatives** (events #5–#12) | All 8 sentences showed progress "—" and **no** one-click confirm. #5–#8 were REVIEW_REQUIRED (the confident ones with the reason "confident match (score 0.907) but the report states no progress or start to apply — its wording is negated or future tense"); #9–#12 were UNMATCHED (scores below 0.45). The confirm attempt on #5 showed the toast "Report carries no progress or start information to apply (its completion/start wording is negated or future tense). Reject it or wait for an actual update." PIP-L5-009 was unchanged (0%, not_started) at that point. **Pass** |
| **§11 regression** | `Completed activity XX102 at rack 3 is now reported at 30%.` → REVIEW_REQUIRED event #13. The candidate row showed PIP-L5-002 "already complete … ×0.85 done" (still rank 1 on its unique tag evidence). The confirm attempt showed the toast "PIP-L5-002 is already complete; lower progress requires explicit planner override. Nothing was written; reject this report if it is wrong." PIP-L5-002 stayed **100% complete, finish 2026-09-26**. **Pass** |
| **§12 positives** (events #16–#20) | XX120 completed → 100%; XX121 finished → 100%; XX122 started → start signal (progress "—"); XX123 installed, 40% → 40%; XX124 installed, 100% → 100%. All REVIEW_REQUIRED (top scores 0.454–0.504), because XX120–XX124 do not exist in the seed schedule. **Extraction pass** |
| **Mobile (F-09)** | 390×844, all 5 views: 390/390, selector visible, 0 off-screen buttons. **Pass** |
| **Health** | 168 API requests; statuses 200, 409, 422, where the 409s and 422 were the deliberate negative tests. Console: 3 resource errors for those deliberate 409/422/409 responses, plus the Chrome issue "A form field element should have an id or name attribute (count: 78)". No unexpected errors |

### 8.3 Evaluator build from the exact commit (Definition of Done #13)

1. `git clone` of the local repository into `%TEMP%\ps_eval`, then `git checkout 5c47051b63a08b206ed030dce1f155886bafc733`. `git rev-parse HEAD` matched, `git status --short` showed 0 entries, and there were 0 `data/*.db` files.
2. `python -m pytest -q -p no:cacheprovider` → **160 passed, 1 warning**.
3. `npm ci && npm run build && npm audit` → OK, **0 vulnerabilities**.
4. `python scripts/run_benchmark.py` → identical to §9.3 (§6.1).
5. `python scripts/reset_demo_db.py` on a fresh DB → 35 activities, 8 mappings. `uvicorn backend.app:app --port 8000` → `/` served "ProgressSync AI"; `semantic_model_available: true`; `reranker_enabled: false`.
6. Browser against this build (asset `index-CKmgpNU_.js`):
   - high-confidence example → AUTO_MATCHED event #1 → Confirm → 0% → 100% complete;
   - ambiguous example → REVIEW_REQUIRED "margin 0.000 to runner-up below 0.12";
   - console: **no messages**.
7. The temporary clone and its DB were deleted afterwards.

This verifies that a build of the exact commit works on this machine. **Deployment to the actual evaluator environment: Not independently verified.** That is outside this session.

### 8.4 Repository hygiene (§13)

- **Secrets scan** (API keys, tokens, passwords, private keys, AWS/GitHub/`sk-` patterns) over all committable files: no secrets. The only hits were prose mentioning "secrets" or "token", and matcher code comments.
- **Personal paths:** none outside `docs/reports`/`docs/prompts`. Those contain only generic `%TEMP%` references in the historical 2026-09-25 audit's environment notes.
- **Stray artifacts:** none staged. `.pytest_cache/`, `__pycache__/`, `benchmark/v2/results/`, `data/progresssync.db`, `frontend-react/dist/` and `frontend-react/node_modules/` are ignored.
- **Guards re-checked:** thresholds `0.82 / 0.12 / 0.45`, the `RERANKER_ENABLED` default "false", and the `one_approval_per_event` index are unchanged.

---

## 9. Definition of Done (§16)

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | F-01 fixed and covered by regression tests | ✅ Verified | §2 F-01; `test_negation.py` (46); browser §11 |
| 2 | F-02/F-13 fixed and covered by regression tests | ✅ Verified | §2 F-02; `test_progress_policy.py` (7); browser regression attempt |
| 3 | F-03 fixed, pending AUTO workflow reachable | ✅ Verified | `test_awaiting.py` (4); browser F-03 row |
| 4 | F-04 fixed, identifier extraction validated | ✅ Verified | `test_identifiers.py` (22); dev then held-out benchmark |
| 5 | F-05 fixed | ✅ Verified | `test_freshness.py` (4) |
| 6 | Full backend tests pass | ✅ Verified | 160 passed (repo, twice, and clean checkout) |
| 7 | Frozen benchmark passes, data and thresholds unaltered | ✅ Verified | held-out 0 silent errors, 0 cross-project, 13/13 unknown; manifest verified by the runner |
| 8 | Reranker remains disabled | ✅ Verified | `reranker_enabled: false` on the served app (clean DB and evaluator build); not run |
| 9 | Frontend builds cleanly | ✅ Verified | §7 (three runs), npm audit 0 |
| 10 | A–E pass again on a clean DB | ✅ Verified | §8.2 (full run after the last UI change, on a freshly reset DB) |
| 11 | Negative safety cases pass | ✅ Verified | §8.2 §11 rows; automated `test_negation.py`, `test_progress_policy.py` |
| 12 | Repository clean and committed | ✅ Verified | commit `5c47051`; `git status --short` → 0 entries after the commit |
| 13 | Evaluator build uses the exact recorded commit | ✅ Verified locally (§8.3); actual evaluator deployment **Not independently verified** | clean checkout of `5c47051`: tests, build, benchmark, served app, browser |

---

## 10. Final Git state

| | |
|---|---|
| Commit | `5c47051b63a08b206ed030dce1f155886bafc733` (`5c47051`) |
| Message | `chore: final SIH evaluation hardening` (with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`) |
| Branch | `sih-final-hardening` |
| Parent | `3b1ffc7` (`main`, unchanged) |
| Size | 61 files changed, 6,531 insertions(+), 606 deletions(−) |
| Remote | Not pushed; not merged; no PR |

This report file was created **after** the commit. It is not part of `5c47051`, and it is currently untracked.

---

## 11. Remaining limitations (as stated in the final report of the session)

- Browser end-to-end testing is manual; there's no automated browser suite in the repo.
- There's no authentication; the plan puts that out of scope.
- The negation handling is a small phrase guard, not language understanding. When it's unsure, it infers nothing.
- There's no workflow to reopen a completed activity; the planner rejects the report instead.
- The benchmark is synthetic and small, so it doesn't measure production accuracy.
- Uploading a schedule through the browser file picker and voice input weren't tested in the browser. Schedule import is covered by the backend tests.
- Cosmetic: the Time Agent says "progress 0% → 0%" when recording a start, and Chrome reports a form-field id/name accessibility notice.

---

## 12. Evaluator deployment instructions

Prerequisites: Python (the session used 3.13.5), Node/npm (the session used Node v24.19.0), and network access once for the model download.

The commit is only in the local repository on branch `sih-final-hardening`. It must be made available to the evaluator machine (e.g. by pushing it, or by copying the repository) before step 1. How it is transferred: **Not recorded**.

```powershell
# 1. Use the exact evaluated commit, never a dirty working tree
git checkout 5c47051
git status                                   # expect a clean tree

# 2. Python environment (pinned versions)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Provision the pinned semantic model ONCE per machine (needs network once)
python scripts/provision_model.py

# 4. Build the React UI (served by FastAPI)
cd frontend-react
npm ci
npm run build
cd ..

# 5. Reset to the clean seeded demo database BEFORE starting the server (stop any running server first)
python scripts/reset_demo_db.py
#    optional throwaway DB: set $env:PROGRESSSYNC_DB="$env:TEMP\progresssync_sih_final.db" before this step AND step 6

# 6. Start the server: UI + API on http://127.0.0.1:8000
uvicorn backend.app:app --port 8000
```

Notes:
- **Do not set `PROGRESSSYNC_USE_RERANKER`.** The reranker must stay off; check that `GET /api/v1/ml/status` shows `"reranker_enabled": false`.
- `GET /api/v1/ml/status` should also show `"semantic_model_available": true`. If the model is missing, the API returns 503 with the provisioning command.
- Demo walkthrough (scenarios A–E and the safety checks): [docs/demo.md](docs/demo.md). API reference: [docs/api.md](docs/api.md). Test and benchmark commands: [docs/testing.md](docs/testing.md).

---

## 13. Items without independent evidence

| Item | Status |
|---|---|
| Deployment on the actual evaluator machine or environment | Not independently verified |
| Reranker behaviour on the hardened code | Not recorded (deliberately not run, §9.4) |
| Exact build sizes of the last two frontend builds | Not recorded |
| Per-category held-out table from the clean-checkout benchmark run | Not recorded (summary only) |
| Human review of the changes | Not independently verified (implemented and verified by the same agent) |
| Voice input; schedule upload through the browser file picker | Not verified in the browser (import is covered by backend tests) |
