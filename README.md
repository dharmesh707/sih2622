# ProgressSync AI

ProgressSync AI is an offline-first execution-intelligence bridge for SIH26122. It turns messy field observations into explainable L5/L6 schedule updates, recomputes CPM, and preserves the evidence and decision trail.

## Setup (once per machine)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt           # pinned versions
python scripts/provision_model.py         # needs network once; downloads the pinned MiniLM model
cd frontend-react; npm ci; npm run build; cd ..
```

### Provision the semantic model

Matching uses `sentence-transformers/all-MiniLM-L6-v2`, pinned to revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` (384-dim). The backend loads it with `local_files_only=True`, so after provisioning everything runs offline.

- `scripts/provision_model.py` downloads that exact revision into the Hugging Face cache (`~/.cache/huggingface`, or `$HF_HOME`).
- On a machine without it, the API returns **503** with the provisioning command, `GET /api/v1/ml/status` reports `semantic_model_available: false`, and `pytest` stops with the same instruction.
- There is **no** lexical or proxy fallback for the semantic score.

## Run

```powershell
python scripts/reset_demo_db.py           # optional: clean seeded demo database
uvicorn backend.app:app                   # UI + API on http://127.0.0.1:8000
```

For UI development, run `cd frontend-react; npm run dev` (http://127.0.0.1:5173, proxies `/api` to :8000). The demo walkthrough is in [docs/demo.md](docs/demo.md), and the API is in [docs/api.md](docs/api.md).

## What it does

1. **Schedule import** (CSV/XLSX) with dependency relationships (FS/SS/FF/SF + lag). A cyclic graph is rejected before anything is saved.
2. **Field report or Time Agent message** → structured event: discipline, identifiers (tags such as `XX102`, `PT-101`, `P-301`, `P 305`, `V-201`, plus line numbers after `line`/`Ln`/`L-`), location, progress, time and source span. Negated or future-tense wording ("not completed yet", "will start tomorrow", "completion is pending") never produces a progress, start or finish. A future `report_date` is rejected.
3. **Matching** within the report's project: ID, lexical (with the YAML terminology map), MiniLM semantic, context and temporal signals. Routing:
   - `AUTO_MATCHED`: score ≥ 0.82 and margin ≥ 0.12.
   - `REVIEW_REQUIRED`: score ≥ 0.45.
   - otherwise `UNMATCHED`. Every decision carries a reason.
   - A confident match whose report states nothing to apply (no progress, no start) is routed to review, not offered as a one-click update.
   - Completed activities are flagged and down-ranked (×0.85) for reports of fresh work.
4. **Human decision**:
   - confirm, reassign to another candidate, manually associate an UNMATCHED event (explicit selection only), or reject;
   - pending AUTO_MATCHED events stay listed under **Awaiting confirmation** in the Review queue until someone confirms, rejects or sends them to review.

   Nothing is written to the schedule without a human confirmation. `APPROVED` and `REJECTED` are terminal, with exactly one approval per event, including under concurrent confirms. Progress is monotonic: a lower-progress report never reopens or lowers an activity (409, nothing written).
5. **Update**: actuals, audit row, optional delay cause, execution memory, and a before/after **forecast CPM** (project finish movement, critical path entered/left, downstream float, at-risk activities, milestones). The forecast and at-risk flags are also refreshed on startup, and on reads whenever the data date has moved since the last snapshot.
6. **Time Agent**: a persisted, project-bound session. It asks a data-driven clarification question and continues the *same* event, and it records only after an explicit "yes".
7. **Views**: Gantt (planned/actual/critical/at-risk/dependencies), planned-vs-actual variance, productivity, delay causes, and institutional-memory search.

## Tests and benchmark

```powershell
pytest -q
python scripts/run_benchmark.py            # frozen held-out split; --split dev, --reranker
```

Last recorded held-out run (84 synthetic cases, fusion baseline, final hardening build):
- 0 silent errors (no wrong AUTO matches) and 100% precision on the 21 auto-matched cases;
- 76.2% top-1 and 92.1% Recall@5;
- all 13 unknown cases UNMATCHED, 0 cross-project candidates.

Most ambiguous matches still go to planner review, by design.

This is a small synthetic benchmark, **not production accuracy**. Details are in [docs/testing.md](docs/testing.md) and [PROGRESS.md](PROGRESS.md).

## Environment variables

| Variable | Effect | Default |
|---|---|---|
| `PROGRESSSYNC_DB` | SQLite file path | `data/progresssync.db` |
| `PROGRESSSYNC_USE_RERANKER` | Enables the legacy logistic-regression reranker. **Not safe**: it produced 6 silent errors on the held-out benchmark (measured 2026-09-26). Leave off; the evaluator build keeps it off. | off |
| `HF_HOME` | Hugging Face cache used for the model | `~/.cache/huggingface` |

## Limitations

- OCR, ASR, XER import and live Primavera integration are out of scope. Voice uses browser Web Speech.
- Storage is SQLite. There is no authentication or authorization.
- CPM has no calendars or resources.
- Negation and future-tense handling is a small deterministic phrase guard, not language understanding. Unusual phrasing may still need planner judgement; when in doubt it infers nothing.
- A line number is line-level evidence (shared by every activity on that line), so line-only reports usually go to review.
- There is no override workflow to reopen a completed activity; the planner rejects the report instead.
