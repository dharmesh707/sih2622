# Architecture

ProgressSync is organized as eight cooperating layers rather than a sequential LLM demo. Ingestion and the schedule graph are shared state: the same activity catalogue feeds both matching and CPM.

- L1: CSV/XLSX, text, diary stub, Time Agent, normalization.
- L2: activities, WBS, dependency DAG, NetworkX CPM, snapshots.
- L3: deterministic event extraction with identifiers, discipline, location, progress, and source span.
- L4: retrieve-then-rank candidate scoring.
- L5: margin decision and planner review.
- L6: actual update, audit, CPM recompute, critical-path diff.
- L7: analytics and historical memory endpoints.
- L8: append-only audit rows.

The backend is FastAPI plus SQLite. The browser is a small static frontend served by FastAPI. DEMO_MODE has no external AI dependency.
