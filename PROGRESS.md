# ProgressSync AI — Next-Phase Progress Log

Plan: [docs/prompts/ProgressSync_Next_Phase_SINGLE_Claude_Pro_Prompt.md](docs/prompts/ProgressSync_Next_Phase_SINGLE_Claude_Pro_Prompt.md)
Baseline audit: [docs/reports/ProgressSync_AI_Final_Audit.md](docs/reports/ProgressSync_AI_Final_Audit.md)

Test environment for every run below: Windows 11, Python 3.13.5, a venv created from `requirements.txt`, and MiniLM cached in `~/.cache/huggingface` unless stated otherwise.

---

## Phase 0 — Re-audit before coding — ✅ Done (2026-09-26)

- Branch `main`, HEAD `3b1ffc7`. The working tree had only untracked `docs/prompts/` and `docs/reports/`.
- Database: SQLite at `PROGRESSSYNC_DB` (default `data/progresssync.db`). No DB file exists in the repo, and startup creates and seeds one. Tests use a per-test tmp DB.
- Entry points:
  - Backend: `uvicorn backend.app:app` ([backend/app.py](backend/app.py)).
  - React: `frontend-react` via `npm run dev`, with Vite proxying `/api` to port 8000.
  - FastAPI `/` still serves the legacy static UI in `frontend/`.
- Test commands: `pytest -q`, `python scripts/run_benchmark.py`, `python scripts/evaluate_reranker.py`, and `npm ci && npm run build` in `frontend-react`.
- Tests run: `pytest -q` → **5 passed** (MiniLM cached).
- Missing documents:
  - `2_ULTIMATE_PROMPT_FINAL.md` is not in the repo or in Downloads. It is not blocking, because the next-phase prompt is self-contained.
  - `~/Downloads/ProgressSync_AI_Final_Prompt_Necessary_Additions (2).md` is an addendum to that missing prompt. It asks for discipline-spreadsheet ingestion, which the authoritative next-phase prompt does not list, so it is not implemented.
- Known issues: B-01…B-17 in the audit report.
- Files changed: `PROGRESS.md` (new).

## Phase 1 — Correctness and safety — ✅ Done (2026-09-26)

Important changes ([backend/app.py](backend/app.py)):
- **`norm()`**: the OCR `o→0` fix now applies only when an `o` touches a digit (`XX1O2`, `RO3`); ordinary words are untouched. Completion inference uses word boundaries, so `incomplete` no longer reads as 100%. Terminology terms are normalized with the same `norm()` before matching, so `CT103` now maps.
- **State machine**:
  - `APPROVED` and `REJECTED` are terminal. Confirm or reject on either returns 409.
  - Human decisions are appended as new `match_decisions` rows, so the system's original decision is kept.
  - A partial unique index allows only one `APPROVED` row per event.
  - The review queue uses each event's latest decision only.
- Only `AUTO_MATCHED` can be confirmed without an explicit `activity_id`. `REVIEW_REQUIRED` and `UNMATCHED` need one (400 otherwise).
- The audit `approval_status` now records `approved`, `reassigned` or `manual_association`.
- Confirming a report with neither progress nor a "started" signal returns 422 instead of writing a no-op audit row. A "started" report sets actual start / in_progress.
- **4xx errors**:
  - A missing event or activity returns 404 (was 500 or 200).
  - An activity from another project returns 409.
  - A report for an unknown project returns 404.
- **Project scoping**:
  - `make_match()` scores only the report's project.
  - Confirm and audit use the report's project.
  - `/review-queue?project_id=`, `GET /api/v1/projects`, and the agent now accept `project_id`.
  - Schedule import creates the project row if it is missing.
- The broken `make_match()` no-candidate fallback (B-16) now records `UNMATCHED`.

Tests run: `python -m pytest -q` → **28 passed** (5 existing + 23 new in [tests/test_safety.py](tests/test_safety.py)). The shared fresh-DB fixture moved into [tests/conftest.py](tests/conftest.py).

Legacy benchmark (`python scripts/run_benchmark.py`, old 9-case held-out, run only as a quick check):
- auto-match precision 100.0%, silent errors 0
- **auto-match rate 100.0%** (was 88.9% before the `norm()` fix)
- Recall@5 100.0%, median latency 120.21 ms

This benchmark is replaced in Phase 8.

Remaining issue: the reranker artifact was trained on features computed with the old broken `norm()`. The reranker is disabled by default and is re-evaluated in Phase 8.

Files changed: `backend/app.py`, `tests/conftest.py`, `tests/test_pipeline.py` (fixture moved), `tests/test_safety.py` (new).

## Phase 2 — Reproducible MiniLM — ✅ Done (2026-09-26)

Important changes:
- The model is pinned: `sentence-transformers/all-MiniLM-L6-v2@1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, loaded with `local_files_only=True` ([backend/app.py](backend/app.py)).
- New [scripts/provision_model.py](scripts/provision_model.py) downloads that revision into the Hugging Face cache. It is a one-time step that needs network.
- A missing model raises `SemanticModelMissing`. The API returns **503** with the provisioning command, `/api/v1/ml/status` reports `semantic_model_available`, and `pytest` exits at session start with the same instruction.
- Docs:
  - README setup, env vars and limitations rewritten.
  - Stale "deterministic proxy" and `DEMO_MODE` claims removed from README, `docs/decisions.md`, `docs/architecture.md`, `docs/demo.md` and `.env.example`.
  - `.env.example` now lists `PROGRESSSYNC_USE_RERANKER`.
  - `docs/testing.md` notes the prerequisite.

Tests run (clean-machine flow, `HF_HOME` pointed at a new empty directory):
1. `python -m pytest -q` → exits immediately: "Semantic model sentence-transformers/all-MiniLM-L6-v2@1110a243fdf4 is not in the local cache. Run once with network access: python scripts/provision_model.py".
2. `POST /api/v1/reports` → **503** with the same message. `ml/status.semantic_model_available` → `false`.
3. `python scripts/provision_model.py` → `provisioned sentence-transformers/all-MiniLM-L6-v2@1110a243fdf4 (dim=384)`.
4. `python -m pytest -q` → **28 passed**.

Remaining issue: the FastAPI root still serves the legacy static UI. This is addressed in Phase 10.

Files changed: `backend/app.py`, `scripts/provision_model.py` (new), `tests/conftest.py`, `README.md`, `.env.example`, `docs/decisions.md`, `docs/architecture.md`, `docs/demo.md`, `docs/testing.md`.

## Phase 3 — React SIH workflow — ✅ Done (2026-09-26)

Important changes:
- **Backend support**:
  - Every system decision stores a human-readable `reason`, e.g. "margin 0.003 to runner-up below 0.12". It is returned by `/reports` and `/review-queue`.
  - Confirm returns the activity, the inserted audit row and `approval_status`.
  - New `GET /projects/{id}/dependencies`.
  - `/audit?project_id=` filter, with the activity code joined in.
- **React**:
  - A project selector in the top bar, backed by `GET /projects`. All views are project-scoped, with no hardcoded project 1.
  - `<Toast>` is now actually rendered. Previously every frontend error was swallowed.
  - The metric "Reports processed" (which counted audit rows) is renamed "Confirmed updates". The latency metric bug is fixed.
  - **AUTO_MATCHED**: the Ingest result card shows code, description, reason, top/runner-up/margin, reranker/fusion stage, extracted fields, source span, the top-3 candidates with ID/lexical/semantic/context/total scores and term evidence, plus **Confirm**. After confirming, `ConfirmResult` shows the schedule change, the audit row and CPM before/after.
  - **REVIEW_REQUIRED**: the top-5 candidate comparison table with radio selection, a comment field, and **Confirm** / **Reassign to X** depending on the choice.
  - **UNMATCHED**: shows why it is unmatched plus a preservation warning. There is no one-click approve; the button stays disabled until an activity is explicitly selected. Audit records `manual_association`.
  - **Gantt** (`ScheduleView`, replaces the 50-row table):
    - planned and actual bars (actual fill = % progress), a today line, and a weekly axis;
    - critical colouring, at-risk row highlight, predecessor codes, float and status;
    - all rows are shown, with a "critical only" filter;
    - live `/activities` + `/dependencies` data.
  - New components: `CandidateList.jsx`, `ConfirmResult.jsx`, `TimeAgentPanel.jsx`.

Tests run:
- `python -m pytest -q` → **28 passed**.
- `npm run build` → OK.

Browser verification (Chrome DevTools MCP, fresh temp DB, `uvicorn` :8000 + Vite :5173):
- Scenario A: `Piping crew completed spool XX102 at rack 3, 100%.` → AUTO_MATCHED PIP-L5-002, reason "top score 0.869 >= 0.82 and margin 0.231 >= 0.12", evidence `spool → piping segment, rack 3 → R03`. Confirm → 0%→100%, not_started→complete, audit #1 `approved`, CPM 156.0d→156.0d.
- Scenario B: ambiguous report → REVIEW_REQUIRED (margin 0.003). Selected rank-2 PIP-L5-023 → "Reassign to PIP-L5-023" → audit #2 `reassigned`, 0%→50%. The event left the queue.
- Scenario C: ZZ-999 → UNMATCHED, "report explicitly names an unknown work package". The action button stays disabled until a manual selection is made.
- Gantt rendered 35 activities and 34 dependencies.
- Console: no JS errors. The only error was a favicon 404, since fixed with an inline icon.

Remaining issues:
- The today line used UTC while the backend uses local dates. Fixed after the check, not re-verified in the browser yet.
- CPM does not move on actuals, and at-risk is always 0. Both are Phase 4.

Files changed: `backend/app.py`, `frontend-react/index.html`, `src/App.jsx`, `src/components/{Layout,CandidateList,ConfirmResult,TimeAgentPanel}.jsx`, `src/views/{IngestView,ReviewView,ScheduleView,AuditView}.jsx`, `src/styles.css`.

## Phase 4 — Schedule + CPM intelligence — ✅ Done (2026-09-26)

Important changes ([backend/app.py](backend/app.py)):
- **Dependency import**:
  - Activity files accept optional `predecessor` (codes separated by `;` or `,`), `relationship` (FS/SS/FF/SF) and `lag` columns.
  - A dependency-only file with `predecessor,successor[,relationship,lag]` is also accepted.
  - Codes resolve within the project. Unknown codes, bad relationships, bad lags, self-links and duplicates become row errors.
  - The whole graph is cycle-checked **before commit**. A cycle returns 409 naming the loop, and nothing is saved.
  - `contractor` and `resource` are now persisted. `parent_activity` is a WBS parent, not a dependency, so it is still not imported.
  - XLSX date cells are parsed.
- **CPM** (still NetworkX, forward and backward pass):
  - Supports FS/SS/FF/SF with lag.
  - With a data date of today it is a *forecast*: actual start and finish fix completed work, in-progress work keeps its remaining duration (`planned × (1 − %)`), and unstarted work cannot start before today.
  - `cpm_state(db, pid)` without a data date is the pure planned network.
  - The `cpm_state` table now stores forecast early start/finish dates.
  - A cycle returns 409 (was an unhandled 500).
- **Confirm impact** (`impact` in the confirm response and in `ConfirmResult`): forecast project finish before and after (dates and days), critical activities entered and left, float changes of downstream activities, at-risk activities after the update, and milestone movement.
  - A milestone is an activity with planned start equal to planned finish, or "milestone" in its description.
- **At-risk rule** (documented in `risk_reason()`): an incomplete activity is at risk if (1) it has not started and its planned start has passed, or (2) its forecast finish is after its planned finish *and* its total float is under 2 days. The reason is stored in the new `activities.at_risk_reason` column, added by an additive `ALTER TABLE` migration in `init_db`.
- **Seed schedule**: same 35 codes and descriptions.
  - Old seed: a single 34-edge chain whose planned dates contradicted its own FS links, so everything was critical.
  - New seed: 5 packages of 7 disciplines with 48 FS links, planned dates derived from that logic, and a start 3 days ago.
  - Demo history: CIV-L5-001 finished one day late.
  - Result: 7 critical activities; 7 at risk (the slipping critical chain).
- **Gantt**: tooltip shows forecast finish and the at-risk reason; the meta column shows the forecast finish.
- `data/sample_schedule.csv` gained `predecessor,relationship,lag` columns whose SS logic matches its dates.

Tests run:
- `python -m pytest -q` → **35 passed** (+7 in [tests/test_schedule.py](tests/test_schedule.py): sample import with deps/fields, dependency-only file with row errors, cycle rejected with nothing saved, FS/SS/FF relationship maths, actual-driven forecast + at-risk + impact, recompute-cycle 409, seed consistency).
- `npm run build` → OK.

One test failed on its first run: `test_actuals_move_the_forecast…` had a wrong expectation. A2's planned start was yesterday, so the late-start rule correctly fired first. The test input was fixed and the code was not changed.

Remaining issues: CPM has no calendars or resources (out of scope). Milestones are a heuristic until the import has an explicit milestone flag.

Files changed: `backend/app.py`, `data/sample_schedule.csv`, `tests/test_schedule.py` (new), `frontend-react/src/components/ConfirmResult.jsx`, `frontend-react/src/views/ScheduleView.jsx`.

## Phase 5 — Analytics + institutional memory — ✅ Done (2026-09-26)

Important changes ([backend/app.py](backend/app.py)):
- **Planned vs actual**: `GET /analytics/variance?project_id=` now returns per-activity start, finish and duration variance plus a summary.
  - Actual duration = actual finish − actual start + 1, and is **null** unless both dates exist.
  - The old WBS average-progress output moved to `GET /analytics/wbs-progress`.
- **Productivity**: `/analytics/discipline-productivity?project_id=` groups by discipline **and activity type**, giving progress, completed count, average planned duration and average *actual* duration (actuals only).
  - Activity type is the description with identifiers, numbers and stopwords removed, e.g. `Erect line XX102 spool 002` → `erect line spool`.
- **Delay causes**:
  - Fixed categories (`GET /delay-cause-categories`).
  - Written from the confirm payload (`delay_cause`, with the comment as notes) or later via `POST /events/{id}/delay-cause`. An invalid cause returns 422 before any write.
  - `delay_causes` gained `project_id`, `activity_id` and `created_at` (additive migration).
  - `/analytics/delay-causes` returns counts plus an ISO-week trend.
- **Institutional memory**: a new `execution_memory` table, upserted on every confirmed actual. It holds project, activity type, discipline, location, planned dates and duration, actual dates, actual duration (null until finished), start/finish/duration variance, delay cause and notes.
  - `GET /memory/similar` filters by project (optional, so cross-project history is possible), discipline and location, and ranks by activity type or description similarity.
  - `GET /memory/summary` aggregates by type.
  - The old endpoint that returned planned duration as actual is gone.
- **React**:
  - Analytics shows the planned-vs-actual table and summary, productivity by discipline and type, delay-cause bars with a weekly trend, and WBS progress.
  - Audit + memory has filterable memory search (description, discipline, location, all-projects toggle), a summary by type, and the terminology source.
  - A `DelayCauseSelect` sits on both confirm paths (Ingest AUTO confirm and Review).

Tests run:
- `python -m pytest -q` → **40 passed** (+5 in [tests/test_analytics.py](tests/test_analytics.py): activity type, actual duration null until finished, variance + delay cause + memory on completion, project-aware memory filters, invalid delay cause blocks the confirm with no write).
- `npm run build` → OK.

Remaining issue: the Analytics and Memory views are not browser-verified yet. That happens in the Phase 9/10 E2E.

Files changed: `backend/app.py`, `tests/test_analytics.py` (new), `frontend-react/src/components/DelayCauseSelect.jsx` (new), `src/views/{AnalyticsView,AuditView,ReviewView,IngestView}.jsx`, `src/styles.css`.

## Phase 6 — Time Agent — ✅ Done (2026-09-26)

Important changes ([backend/app.py](backend/app.py)):
- New tables `agent_sessions` (project, state `idle|clarifying|awaiting_confirmation`, pending event, selected activity, rounds) and `agent_messages` (every user and agent turn). `session_id` is created when it is missing and restored when it is present. `GET /agent/sessions/{id}` returns the state and the transcript.
- The first message goes through the normal `report()` pipeline and creates **one** event.
- Follow-ups while clarifying are appended to that event's text, **re-extracted and re-matched on the same event** (`rematch_event`). Superseded candidate rows are replaced; every decision row is kept.
- Clarification questions are generated from the data. In order, the agent asks:
  - for an identifier/location when the report is UNMATCHED;
  - which activity, when several candidates share the identifier;
  - which location, when candidate locations differ;
  - for the location or discipline, when missing;
  - for progress, when there is neither a % nor a "started" signal;
  - otherwise, which of the top codes.
  - A reply that names a candidate code counts as an explicit supervisor selection.
- Nothing is written without an explicit **yes**. "yes" calls the same `apply_update` (audit actor `supervisor via time agent <session>`). "no" appends a `REVIEW_REQUIRED` decision so the event goes to the planner queue. After 2 unresolved clarification rounds the event is left for planner review.
- If a planner confirms or rejects the event elsewhere, the session resets instead of acting on a stale event.
- React `TimeAgentPanel`: server-side session with its id remembered per project in `localStorage` (wrapped in try/catch), transcript restored on reload, state shown, "Yes, record it" / "No, send to planner" buttons, "New conversation".

Tests run:
- `python -m pytest -q` → **45 passed** (+5 in [tests/test_time_agent.py](tests/test_time_agent.py): clarification → same event → confirm → audit + stored transcript, session isolation, "no" → review with no write, unresolved after max rounds → review, pick by code → confirm).
- `npm run build` → OK.

Sample conversation (TestClient, fresh DB):
```
> XX102 started at 9.
< Which location is this at: R03, Unit 2?
> Rack 3.
< Matched to PIP-L5-002 (Erect line XX102 spool 002, R03); score 0.935, margin 0.449. I will record actual start today. Confirm? (yes / no)
> yes
< Recorded on PIP-L5-002: … status not_started → in_progress, actual start <today>, audit #1 …
```

Remaining issue: the time of day ("at 9") is extracted but only the date is stored for actuals. Voice stays browser Web Speech (prototype scope).

Files changed: `backend/app.py`, `tests/test_time_agent.py` (new), `frontend-react/src/components/TimeAgentPanel.jsx`.

## Phase 7 — Terminology source of truth — ✅ Done (2026-09-26)

Important changes:
- [data/terminology_map.v1.yaml](data/terminology_map.v1.yaml) is now the only source. `load_terms()` reads it at **every** startup, validates it (field term, canonical term and a valid discipline required; duplicates after `norm()` rejected) and replaces the `terminology_map` table contents. The hardcoded list in `app.py` is removed.
- The old hardcoded list had 10 entries and the YAML had 5. The three real mappings that existed only in code (`erection → erect`, `boltup → bolting`, `cable pull → cable installation`) were moved into the YAML.
- Two no-ops were dropped: `rack-3` (normalizes to `rack 3`) and `pump → pump`.
- `/terminology-map` serves the loaded rows. The React Audit view shows the version and source file. The matcher uses the loaded rows, as before.
- `pyyaml` was added to `requirements.txt`; previously it arrived only transitively.

Tests run: `python -m pytest -q` → **56 passed** (+11 in [tests/test_terminology.py](tests/test_terminology.py): API equals YAML, each of the 8 YAML mappings applied by the matcher, `spool` and `rack-3` examples, YAML edits take effect, duplicate and invalid files rejected).

Files changed: `backend/app.py`, `data/terminology_map.v1.yaml`, `requirements.txt`, `tests/test_terminology.py` (new).

## Phase 8 — Benchmark hardening — ✅ Done (2026-09-26)

Important changes:
- New deterministic benchmark [scripts/build_benchmark.py](scripts/build_benchmark.py) → `benchmark/v2/` (seed 26122, fixed data date 2026-09-01).
  - Schedule: 82 activities in project 2, in canonical schedule language, with near-duplicate lines, pumps, transmitters, feeders and vessels.
  - Distractor: project 3 holds 27 look-alike activities.
  - Cases: 140 hand-written field paraphrases, 14 per category:
    - exact, synonym, abbreviation, typo/OCR (O for 0), near duplicate, unknown activity;
    - missing timestamp (no time in text) vs cases with times ("at 14:30", "@ 16:00");
    - wrong discipline, granularity mismatch (package-level reports, truth = none);
    - terminology-map terms (`hydrotest`, `boltup`, `cable pull`, `spool` + `rack 3`).
  - Split: 56 dev / 84 held-out. The held-out set includes 13 unknown and 8 granularity no-truth cases.
  - Frozen by SHA-256 in `benchmark/v2/MANIFEST.json`. The runner refuses to score changed files.
- [scripts/run_benchmark.py](scripts/run_benchmark.py) was rewritten to use the **production path**: import through `/schedule/import`, then each case through `POST /reports` (extract → `make_match` with terminology, discipline filter, unknown signal and project scoping) with `report_date` = data date for reproducible temporal scores.
  - It reports auto precision, silent errors, routing, top-1, Recall@5, no-truth handling, cross-project candidate count, median latency and a per-category table.
  - It writes per-case JSON to `benchmark/v2/results/`.
- `POST /reports` accepts an optional `report_date` (defaults to today), which is needed for reproducible dates.
- **Matcher defect fix (audit B-14)**:
  - The activity-code token check gave 0.82 ID credit to every `PIP-*` activity because "pip" is a substring of "piping". Code parts now count only as whole tokens that contain a digit.
  - Diagnosed on the **dev** split only. The held-out set was not used to choose the fix.
  - Regression test added (`test_code_prefix_inside_a_word_is_not_identifier_evidence`).
- The legacy `scripts/generate_corpus.py`, `benchmark/generated/` and the reranker scripts are kept only as reranker-training lineage.

Benchmark actually run (`python scripts/run_benchmark.py [--split dev] [--reranker]`):

| Run | Split | Auto prec. | Silent errors | AUTO / REVIEW / UNM | Top-1 | R@5 | Unknown → UNMATCHED | Cross-project |
|---|---|---:|---:|---|---:|---:|---:|---:|
| baseline, before B-14 fix | dev (56) | 100.0% (13) | 0 | 23.2 / 76.8 / 0.0% | 69.4% | 98.0% | 0/1 | 0 |
| baseline, before B-14 fix | held-out (84) | 100.0% (7) | 0 | 8.3 / 81.0 / 10.7% | 57.1% | 82.5% | 9/13 | 0 |
| reranker on, before fix | held-out (84) | 58.1% (62) | **26** | 73.8 / 19.0 / 7.1% | 57.1% | 82.5% | 6/13 | 0 |
| baseline, after B-14 fix | dev (56) | 100.0% (15) | 0 | 26.8 / 69.6 / 3.6% | 83.7% | 98.0% | 1/1 | 0 |
| **baseline, after B-14 fix (final)** | **held-out (84)** | **100.0% (13)** | **0** | **15.5 / 67.9 / 16.7%** | **76.2%** | **92.1%** | **13/13** | **0** |
| reranker on, after fix | held-out (84) | 88.9% (54) | **6** | 64.3 / 28.6 / 7.1% | 76.2% | 92.1% | — | 0 |

Median server latency is 37–68 ms per report (82 activities, local CPU).

Interpretation:
- The fusion baseline is **safe** (0 wrong auto-matches, all unknowns unmatched) but **conservative**: most real matches go to planner review. Near-duplicate cases correctly never auto-match (top-1 0%, all REVIEW).
- The legacy **reranker is unsafe on this benchmark** (6–26 silent errors). It must stay disabled (the default). It was trained on the old corpus with the pre-fix normalization.
- This is a small synthetic corpus, not production accuracy.

Tests run: `python -m pytest -q` → **57 passed**.

Remaining issues: the reranker needs retraining on realistic data before it can be enabled (not in scope). The extractor does not treat bare line numbers ("line 2104") or single-letter tags ("P-301") as identifiers; this is visible in the abbreviation and near-duplicate categories.

Files changed: `backend/app.py`, `scripts/build_benchmark.py` (new), `scripts/run_benchmark.py` (rewritten), `benchmark/v2/*` (new), `tests/test_safety.py`.

## Phase 9 — Testing — ✅ Done (2026-09-26)

- Added [tests/test_matching.py](tests/test_matching.py) (7 tests: exact → AUTO correct, synonym via terminology, abbreviation, typo/OCR zero, near-duplicate never AUTO, unknown → UNMATCHED, wrong discipline never auto-matches a wrong activity).
- Coverage against the prompt's list:
  - backend: normalization, terminology, completion inference, multi-project, duplicate confirmation, reject-after-approve, missing event and activity, wrong-project activity, dependency import, dependency cycle, actual duration, at-risk;
  - matching: all 7 categories;
  - Time Agent: persistence, clarification, same-event continuation.
- Browser E2E was run with the Chrome DevTools MCP (results under Phase 10). It is manual; there is no automated browser suite in the repo.

Tests run: `python -m pytest -q` → **64 passed**.

## Phase 10 — Release cleanup + final verification — ✅ Done (2026-09-26)

Important changes:
- **One supported UI**: FastAPI now serves the built React app (`frontend-react/dist`) at `/` and `/assets`. If it is not built, `/` returns 503 with the build command.
  - The legacy static UI `frontend/` was **removed**. It hardcoded project 1 and broke against the new analytics API. It is recoverable from git history (`3b1ffc7`).
- `scripts/reset_demo_db.py` deletes and re-seeds the configured `.db` file (35 activities, 8 terminology mappings).
- `requirements.txt` is pinned: fastapi, uvicorn, pydantic, networkx, openpyxl, httpx, pytest, python-multipart, PyYAML, sentence-transformers, transformers, torch, and scikit-learn (for the reranker scripts). The frontend is pinned by `frontend-react/package-lock.json`, installed with `npm ci`.
- The FastAPI `@on_event` hook became a `lifespan` handler, and `datetime.utcnow()` became `datetime.now(timezone.utc)`. Pytest warnings dropped from **306 to 1**; the remaining one comes from FastAPI's own TestClient import.
- Completed activities report `total_float = null` (it was a meaningless −1.0d), and the Gantt shows "—". `snapshot_diff` is guarded for that.
- Removed the empty root `package-lock.json` (audit B-17).
- Docs rewritten: `README.md`, `docs/api.md`, `docs/demo.md`, `docs/testing.md`, `docs/architecture.md`, `frontend-react/README.md`. `FINAL_PROTOTYPE_QUICK_START.md` and `FINAL_PROTOTYPE_TECHNICAL_HANDOVER.md` are marked as historical snapshots of `12b4376`.

Final verification actually run:
- `python -m pytest -q` → **64 passed, 1 warning**.
- `cd frontend-react && rm -rf node_modules dist && npm ci && npm run build` → OK (JS 259.44 kB, 79.61 kB gzip).
- `python scripts/run_benchmark.py` (frozen held-out, final code) → 84 cases, auto precision 100.0% (13), **0 silent errors**, AUTO/REVIEW/UNM 15.5/67.9/16.7%, top-1 76.2%, R@5 92.1%, 13/13 unknown UNMATCHED, 0 cross-project candidates, median 51.7 ms.
- `python scripts/reset_demo_db.py` → `reset …\data\progresssync.db: 35 seeded activities, 8 terminology mappings`.

**Browser E2E** (Chrome DevTools MCP, `uvicorn backend.app:app --port 8000` serving the built UI, freshly reset demo DB):
- **A**: high-confidence example → AUTO_MATCHED PIP-L5-002 (0.965, margin 0.531, evidence `spool → piping segment, rack 3 → R03`). Confirm → 0→100%, complete, audit #1 `approved`, CPM impact panel (finish 2026-10-30 → 2026-10-30).
- **D**:
  - `XX103 started at 9.` → "Where is this work? My best guess is PIP-L5-009 … at R03".
  - `Rack 3.` → same event #2 → AUTO_MATCHED 0.879 → "Confirm? (yes / no)".
  - **Yes, record it** → in_progress, actual start, audit #2, actor `supervisor via time agent 9a661daf`.
  - The session transcript was restored after a page reload.
- **B**: ambiguous example → REVIEW_REQUIRED (0.451, margin 0.018). Top-5 comparison. Selected rank 2 PIP-L5-030 with a comment → **Reassign** → audit #4 `reassigned`, 0→50%.
- **C**: ZZ-999 → UNMATCHED ("report explicitly names an unknown work package"). The action button stays disabled with no selection. The observation was still preserved in the queue at the end, with no audit row.
- **E**:
  - `Foundation concrete poured at Area A, 40%.` → REVIEW_REQUIRED. Confirmed CIV-L5-008 with delay cause `weather` → **forecast finish 2026-10-30 → 2026-10-27 (−3.4d)**, PIP-L5-009 float 12.0 → 8.6d, at-risk list emptied.
  - Gantt: 35 activities, 48 dependencies, planned/actual/critical bars.
  - Analytics: variance for 5 started activities, productivity with actual durations, delay cause weather ×1 (2026-W39).
  - Memory: 5 records, actual duration n/a until finished, delay cause and notes shown. Terminology shows 8 YAML rows.
- Network: 60/60 API requests returned 200. Console: no errors or warnings.

Files changed: `backend/app.py`, `requirements.txt`, `scripts/reset_demo_db.py` (new), `frontend/` (deleted), `package-lock.json` (deleted), `frontend-react/src/views/ScheduleView.jsx`, the docs listed above.

---

## Final Verified State (2026-09-26)

| Area | State | Evidence |
|---|---|---|
| Backend | ✅ Project-scoped, safe state machine (APPROVED/REJECTED terminal, append-only decisions, one approval per event enforced by index), clean 4xx, 503 when the model is missing | 64 pytest; E2E A–E |
| Database | ✅ SQLite with additive migrations (`at_risk_reason`, delay-cause columns, `execution_memory`, `agent_sessions`, `agent_messages`), reset script. ⚠️ No FKs; PostgreSQL out of scope | `reset_demo_db.py` run |
| ML | ✅ Pinned MiniLM with provisioning script and clean-machine message; `norm()` and B-14 fixed. ⚠️ Legacy reranker unsafe (6 silent errors), off by default | Phase 2 clean run; benchmark |
| React | ✅ Only supported UI, served by FastAPI; AUTO confirm, top-5 compare/reassign, UNMATCHED safety, project selector, error toasts | E2E A–E, `npm ci && npm run build` |
| Time Agent | ✅ Persisted sessions, data-driven clarification, same-event continuation, explicit yes/no, audit | test_time_agent (5), E2E D |
| CPM | ✅ FS/SS/FF/SF + lag, cycle rejection, progress-aware forecast from actuals, impact (finish, critical, float, risk, milestones) | test_schedule (7), E2E E (−3.4d) |
| Gantt | ✅ Live planned/actual/progress/predecessors/critical/at-risk/forecast | E2E |
| Analytics | ✅ Planned-vs-actual variance, productivity by discipline and type, delay causes with trend | test_analytics (5), E2E |
| Memory | ✅ Persisted execution memory, actual duration null until finished, project-aware search | test_analytics, E2E |
| Testing | ✅ 64 backend tests; ⚠️ browser E2E is manual (MCP), not an automated suite | this log |
| Benchmark | ✅ Frozen v2 (84 held-out, 10 categories) through the production path: 0 silent errors, 76.2% top-1. ⚠️ Synthetic and small; baseline is conservative (15.5% AUTO) | run_benchmark.py |
| Release | ✅ Pinned deps (fresh venv: `pip install -r requirements.txt` exit 0, then 64 passed), reset script, accurate docs, no fallback/static/mock claims | this log |

---

## Final SIH evaluation hardening (2026-09-26)

Plan: [docs/prompts/ProgressSync_AI_Final_SIH_Evaluation_Ready_Hardening_Prompt.md](docs/prompts/ProgressSync_AI_Final_SIH_Evaluation_Ready_Hardening_Prompt.md). Findings come from [docs/reports/ProgressSync_AI_Final_Audit.md](docs/reports/ProgressSync_AI_Final_Audit.md). Order followed: F-01 → F-02/F-13 → F-03 → F-04 → F-05 → hardening.

| Item | Status | Change | Tests |
|---|---|---|---|
| F-01 negation / future tense | ✅ | `NEGATED_OR_FUTURE` guard. A guarded phrase blocks the completion/start verb it governs, and an unguarded positive verb still counts. A confident match with nothing to apply is routed to REVIEW with a reason. A confirm returns 422 with an explanation. `inference_note` preserves why | `test_negation.py` (46) |
| F-02 / F-13 progress regression | ✅ | `apply_update` refuses to reopen a complete activity or lower progress (409, nothing written); a repeat 100% keeps the first finish date. Completed activities are flagged and ×0.85 for fresh-work reports. A concurrent-confirm race that surfaced a 500 is mapped to 409 (one approval still guaranteed) | `test_progress_policy.py` (7) |
| F-03 pending AUTO reachable | ✅ | `GET /awaiting-confirmation`, `POST /events/{id}/send-to-review`, and an "Awaiting confirmation" section in Review with Confirm / Send to review / Reject | `test_awaiting.py` (4) |
| F-04 identifiers | ✅ | Single-letter tags (`P-301`, `P 301`, `V-201`, `T-101`); line numbers only after `line`/`Ln`/`L-`/`Line No.`; `%` is never a tag; whole-token matching. Line numbers are line-level evidence (0.82, no lexical/semantic floors). A first version gave them 1.0 with floors and dropped **dev** top-1 from 83.7% to 71.4%; that was diagnosed on dev only, then fixed | `test_identifiers.py` (22) |
| F-05 stale forecast | ✅ | Snapshots store `data_date`; startup and `GET /activities`/`/critical-path` recompute when it moved | `test_freshness.py` (4) |
| F-08 future report_date | ✅ | 422 at the API boundary | `test_hardening.py` |
| F-09 mobile | ✅ | Selector kept at ≤850 px; `min-width:0` and `minmax(0,1fr)` fixes; file input constrained. 390×844: all five views 390/390, selector visible, no off-screen buttons | browser |
| F-10 agent isolation | ✅ | A session from another project starts a new session; `GET /agent/sessions/{id}?project_id=` returns 404 on mismatch | `test_hardening.py` |
| F-11 short codes | ✅ | `code_named()` does whole-token matching | `test_hardening.py` |
| F-15 demo DB | ✅ | Local `data/progresssync.db` reset (4 audit rows / 5 reports → 0; 35 activities). Gitignored and never committed | reset script |
| Demo sample | ✅ | The UI "ambiguous example" is now `Pump CT103 installed at Unit 2, 50%.` (five seeded CT-103 pumps, a real tie). The old spool sample falls to UNMATCHED once scenario A completes PIP-L5-002, because of F-13 | browser |

Release protocol (all on the final code):
- **9.1** `python -m pytest -q` → **160 passed, 1 warning** (FastAPI TestClient re-export).
- **9.2** dev: 56 cases, auto precision 100% (22), 0 silent errors, AUTO/REVIEW/UNM 39.3/57.1/3.6%, top-1 83.7%, R@5 98.0%, 0 cross-project.
- **9.3** frozen held-out (manifest verified by the runner; benchmark data, labels and thresholds unchanged): 84 cases, **auto precision 100% (21, was 13)**, **0 silent errors**, AUTO/REVIEW/UNM 25.0/58.3/16.7%, top-1 76.2%, R@5 92.1%, unknown 13/13 UNMATCHED, **0 cross-project**, median 74.2 ms.
- **9.4** reranker not run and not enabled (`reranker_enabled: false` confirmed on the served app).
- **9.5** `npm ci && npm run build && npm audit` → OK, 0 vulnerabilities. Re-run after the last UI change; see the final report.
- **9.6** `PROGRESSSYNC_DB=%TEMP%\progresssync_sih_final.db` + `python scripts/reset_demo_db.py` → 35 activities, empty audit/queue/awaiting.
- **§10 browser** (built UI served by FastAPI, clean DB, re-run in full after the last UI change):
  - **A:** AUTO_MATCHED PIP-L5-002 0.965 with evidence → Confirm → 0→100% complete, audit #1, CPM panel.
  - **F-03:** an unconfirmed XX104 report listed under Awaiting confirmation → confirmed there → the list disappears; a second confirm returns 409; 1 audit row.
  - **B:** CT103 → REVIEW_REQUIRED margin 0.000 (ROT-L5-004/011/018) → reassigned to ROT-L5-011, audit `reassigned`.
  - **C:** ZZ-999 → UNMATCHED, the button stays disabled with no selection.
  - **D:** `XX103 started at 9.` → location question → `Rack 3.` → same event #14 AUTO 0.879 → Yes → audit #4.
  - **E:** CIV-L5-008 40% with delay cause `weather` → forecast finish 2026-10-30 → 2026-10-27 (−3.4d), float changes, at-risk emptied; Gantt 35/48; variance; delay causes; memory.
- **§11 negatives in the browser:** all 8 sentences show progress "—" and no one-click confirm; the confirm attempt shows the 422 toast. `Completed activity XX102 … 30%` → confirm on PIP-L5-002 shows the 409 toast; the activity stays 100% complete with its finish date.
- **§12 positives:** 100 / 100 / start / 40 / 100 extracted (they route to review because XX120–XX124 are not in the seed).
- Console: only the three expected 409/422 resource logs from the deliberate negative tests, plus the old form-field-id accessibility notice.

Remaining limitations: see README "Limitations". The browser E2E is manual (MCP), not an automated suite in the repo. No authentication (explicitly out of scope). The benchmark is synthetic.
