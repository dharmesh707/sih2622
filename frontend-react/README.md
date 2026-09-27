# ProgressSync AI — React frontend

This is the only supported UI. It uses the FastAPI `/api/v1` contract ([docs/api.md](../docs/api.md)) with live data only; there are no mock states.

```powershell
npm ci
npm run dev      # http://127.0.0.1:5173, proxies /api to the backend on :8000
npm run build    # dist/, which FastAPI then serves at http://127.0.0.1:8000/
```

## Views

A project selector in the top bar scopes every view.

1. **Ingest**:
   - A field report produces a decision card with the reason, extracted fields, top-3 candidates and evidence.
   - **Confirm** is available for AUTO_MATCHED, with an optional delay cause.
   - Schedule import (CSV/XLSX with dependencies).
   - The Time Agent chat, with a persisted session, clarification, and yes/no confirmation.
2. **Review queue**: top-5 candidate comparison with explicit selection. The action changes between confirm, reassign and manual association (for UNMATCHED). Also comment, delay cause and reject.
3. **Schedule**: Gantt with planned and actual bars, progress, predecessors, critical path, at-risk flags and forecast finish; plus CPM recompute.
4. **Analytics**: planned-vs-actual variance, productivity by discipline and activity type, delay causes and trend, WBS progress.
5. **Audit + memory**: audit trail, institutional-memory search (description, discipline, location, all projects), and the terminology map.
