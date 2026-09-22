# ProgressSync AI Quick Start

**Project:** ProgressSync AI - SIH26122  
**Audited revision:** `12b4376`  
**Audit date:** 2026-09-22

## What This Prototype Does

ProgressSync turns a field observation such as:

```text
Piping crew completed spool XX102 at rack 3, 100%.
```

into a stored field report and execution event, ranks schedule activities, records evidence and confidence, routes the result to automatic matching/review/unmatched handling, and lets a planner confirm a schedule update. Confirmation writes actual progress/status, an audit row, and a before/after CPM snapshot.

It is a local prototype. It does not provide authentication, production OCR/ASR, live Primavera integration, durable Time Agent conversations, or production deployment packaging.

## Start the Backend

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PROGRESSSYNC_DB="data/progresssync.db"
uvicorn backend.app:app --reload
```

Open `http://127.0.0.1:8000`. FastAPI serves the current default static UI.

The local semantic model is `all-MiniLM-L6-v2` and is loaded with `local_files_only=True`. Matching therefore requires the model to be available locally. The optional reranker is enabled only with:

```powershell
$env:PROGRESSSYNC_USE_RERANKER="true"
```

`DEMO_MODE=true` appears in the README and `.env.example`, but the backend does not read it and it does not change runtime behavior.

## Start the React UI

The React app is separate from the FastAPI-served static UI:

```powershell
cd frontend-react
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to the backend on port 8000. The React app has five state-switched views, not URL routes:

1. Ingest
2. Review queue
3. Schedule
4. Analytics
5. Audit + memory

## Try the Main Workflow

1. In **Ingest**, submit `Piping crew completed spool XX102 at rack 3, 100%.`.
2. Inspect the returned decision, top score, runner-up, margin, extracted discipline, identifier, and location.
3. Submit `Piping crew working at rack 3, spool aligned, 50%.` to create a review case.
4. Open **Review queue** and inspect candidate evidence and score components.
5. Confirm the top candidate. The backend updates progress/status and writes an audit record.
6. Open **Schedule** and recompute CPM if needed.
7. Open **Audit + memory** to inspect old/new values, evidence, actor, score, and terminology.
8. Send `Pump CT103 installed at Unit 2, 50%.` through Time Agent. It calls the same report pipeline.
9. Send `ZZ-999 unknown activity at offshore platform, 20%.` and verify that it is preserved as unmatched/review rather than forced into the schedule.

## Important Files

- [backend/app.py](backend/app.py): entire FastAPI backend, SQLite schema, extraction, matching, reranker use, CPM, audit, and routes.
- [tests/test_pipeline.py](tests/test_pipeline.py): five backend integration tests.
- [frontend/app.js](frontend/app.js): default static frontend.
- [frontend-react/src](frontend-react/src): separate React frontend.
- [scripts/run_benchmark.py](scripts/run_benchmark.py): held-out benchmark runner.
- [scripts/build_reranker_dataset.py](scripts/build_reranker_dataset.py): builds reranker features/labels.
- [scripts/train_reranker.py](scripts/train_reranker.py): trains the logistic-regression artifact.
- [ml_artifacts/reranker_v0.1.pkl](ml_artifacts/reranker_v0.1.pkl): optional trained artifact.
- [data/sample_schedule.csv](data/sample_schedule.csv): five-row sample import; it is not loaded automatically at startup.
- [data/terminology_map.v1.yaml](data/terminology_map.v1.yaml): checked-in YAML source; startup currently uses hardcoded terminology instead.

## Matching Rules

Without the reranker:

- `AUTO_MATCHED`: fused score >= `0.82` and margin >= `0.12`.
- `REVIEW_REQUIRED`: fused score >= `0.45` but auto conditions fail.
- `UNMATCHED`: fused score < `0.45`.

Explicit unknown package language such as `ZZ-999` forces `UNMATCHED`.

The baseline score is:

```text
(0.30 * ID
 + 0.15 * lexical
 + 0.25 * MiniLM semantic
 + 0.30 * context) * temporal factor
```

The optional reranker uses logistic regression over 12 stored features and thresholds of `0.90` auto, `0.50` review, and `0.10` probability margin.

## API Shortlist

All backend API routes use `/api/v1`:

```text
POST /reports
GET  /events/{id}
GET  /events/{id}/candidates
GET  /review-queue
POST /events/{id}/confirm
POST /events/{id}/reject
GET  /projects/{id}/activities
POST /projects/{id}/schedule/import
POST /projects/{id}/recompute
GET  /projects/{id}/critical-path
GET  /analytics/discipline-productivity
GET  /analytics/delay-causes
GET  /analytics/variance
GET  /memory/similar
GET  /audit
GET  /terminology-map
GET  /ml/status
POST /agent/message
```

Example:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/v1/reports `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"text":"Piping crew completed spool XX102 at rack 3, 100%.","source":"text"}'
```

## Verify the Repository

```powershell
pytest -q
python scripts/run_benchmark.py
cd frontend-react
npm run build
```

Audit results on 2026-09-22:

- `pytest -q`: **5 passed**, with deprecation warnings.
- Held-out benchmark: **9 synthetic cases**, 100.0% auto-match precision, 0 silent errors, 88.9% auto rate, 11.1% review rate, 100.0% Recall@5, and 47.74 ms median latency in that local run.
- These are prototype/synthetic results, not production accuracy claims.

## Current Gaps to Know Before Editing

- Matching and confirmation are hardcoded to project 1 in important paths.
- The Time Agent is one-shot; `session_id` is accepted but not stored or used.
- The React app is separate from the default static UI and hardcodes project 1.
- Imported schedule dependencies are not created.
- SQLite tables have no declared foreign keys or migration system.
- Delay causes have a read endpoint but no write path.
- Similar history reports planned duration as `actual_duration`.
- `at_risk` is not calculated.
- The README/docs describe a semantic fallback proxy, but current code requires local MiniLM.

## Safe Change Rules

1. Read [backend/app.py](backend/app.py) and the relevant test before changing behavior.
2. Treat code and executed tests as authoritative over old docs/PDFs.
3. Preserve API response fields unless deliberately versioning the API.
4. Never force an uncertain match into the schedule.
5. Preserve candidate evidence, score components, margins, and audit old/new values.
6. Do not modify held-out data to improve metrics.
7. Add a focused test for every behavior change.
8. Run `pytest -q` after backend changes.
9. Run `npm run build` from `frontend-react` after frontend changes.
10. Run the benchmark when changing matching, thresholds, features, or ML artifacts.

## First-Hour Path

- **0-10 minutes:** Read the problem, pipeline, and matching rules above.
- **10-20 minutes:** Start the backend and open the default UI.
- **20-30 minutes:** Process a report and inspect its event/candidates response.
- **30-40 minutes:** Read `extract_event`, `score_candidate`, `make_match`, and reranker loading.
- **40-50 minutes:** Read the `SCHEMA`, `init_db`, `apply_update`, and `recompute` functions.
- **50-60 minutes:** Start React, trace `api.js` into the five views, and run the tests.

## Ten Questions to Answer

1. Which UI is served at FastAPI `/`?
2. Where does SQLite initialize its tables?
3. What does event extraction actually detect?
4. What are the baseline score weights?
5. What are the three decision states and thresholds?
6. Is the reranker enabled by default?
7. Which tables store evidence and audit data?
8. What does confirmation update?
9. Is the Time Agent multi-turn?
10. Why are the benchmark numbers not production metrics?

For the full schema, endpoint contracts, ML details, limitations, roadmap, and open SIH submission issues, read [FINAL_PROTOTYPE_TECHNICAL_HANDOVER.md](FINAL_PROTOTYPE_TECHNICAL_HANDOVER.md).
