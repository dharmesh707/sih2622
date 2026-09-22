# ProgressSync AI — React frontend

This is a React/Vite rewrite of the original `frontend/index.html`, `frontend/app.js`, and `frontend/styles.css` while keeping the existing FastAPI `/api/v1/*` contract.

## Development

From this directory:

```powershell
npm install
npm run dev
```

Keep the existing FastAPI backend running on `http://127.0.0.1:8000`. Vite proxies `/api` requests to that backend.

Open `http://127.0.0.1:5173`.

## Production build

```powershell
npm run build
npm run preview
```

The build output is `dist/`.

## Included flows

- Ingest: text report, browser speech input, samples, schedule import, Time Agent, metrics
- Review: candidate evidence, component scores, approve/reject, post-confirm CPM diff
- Schedule: activities, actual progress, float, state, CPM recompute
- Analytics: discipline productivity, WBS variance, delay causes
- Audit + memory: audit trail, institutional memory, terminology map

No backend endpoint or data model is changed by this frontend rewrite.
