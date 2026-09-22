# ProgressSync AI

ProgressSync AI is an offline-first execution-intelligence bridge for SIH26122. It turns messy field observations into explainable L5/L6 schedule updates, recomputes CPM, and preserves the evidence and decision trail.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DEMO_MODE='true'
uvicorn backend.app:app --reload
```

Open `http://127.0.0.1:8000`. DEMO_MODE uses deterministic extraction, matching, and CPM; no paid credentials or network connection are required.

## Pipeline

1. Schedule CSV/XLSX is validated into a SQLite activity catalogue and dependency graph.
2. Text, diary, spreadsheet, and Time Agent input become structured events with source spans.
3. Candidates are ranked with ID, lexical, semantic proxy, context, and temporal signals.
4. `AUTO_MATCHED` requires score >= 0.82 and margin >= 0.12. Lower-confidence cases enter review; weak cases remain unmatched.
5. Planner confirmation writes actuals, an immutable audit row, and a before/after CPM snapshot.

The frontend has five views: Ingest, Review queue, Schedule, Analytics, and Audit + memory.

## Tests and benchmark

```powershell
pytest -q
python scripts/generate_corpus.py
python scripts/run_benchmark.py
```

The benchmark writes its generated corpus under `benchmark/generated/`; held-out cases are kept separate and evaluated only by the runner. Results are printed from the actual run.

## Limitations

The semantic signal is a deterministic lexical proxy when local sentence-transformers are unavailable. OCR, ASR, and live Primavera integration are intentionally stubs for v1. The SQLite schema is shaped for a PostgreSQL migration, but this prototype does not claim production scale or authorization.
