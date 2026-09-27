# Architecture

- **Backend**: a single FastAPI app, [backend/app.py](../backend/app.py), on SQLite. Tables are created with `CREATE TABLE IF NOT EXISTS`, plus additive `ALTER TABLE` migrations in `init_db`.
- **UI**: the React/Vite app in `frontend-react/`, built into `frontend-react/dist` and served by FastAPI at `/`. `npm run dev` on :5173 proxies `/api` for development.
- **Inference**: local only. `sentence-transformers/all-MiniLM-L6-v2` is pinned to a revision and provisioned once; no network after that.

## Pipeline

1. **Ingest**: text or Time Agent message → `field_reports` → `extract_event()`, a regex extraction of:
   - discipline, location, progress, quantity, time and source span;
   - identifiers: multi-letter and single-letter tags, plus line numbers only after `line`/`Ln`/`L-`.

   A small deterministic guard (`NEGATED_OR_FUTURE`) stops negated or future-tense completion/start wording from producing progress, start or finish.
2. **Match** (`make_match`, report's project only):
   - Each activity gets ID, lexical (terminology-mapped), MiniLM semantic and context scores, multiplied by a temporal factor. The fused score is `0.30·ID + 0.15·lex + 0.25·sem + 0.30·ctx`.
   - ID evidence levels: a tag gives 1.0 (and floors lexical/semantic). A line number or an identifier-like code part gives 0.82, because it is shared by every activity on the line. All comparisons are whole-token.
   - Completed activities are multiplied by 0.85 for reports of fresh work.
   - Routing: AUTO_MATCHED (score ≥ 0.82 and margin ≥ 0.12), REVIEW_REQUIRED (score ≥ 0.45), else UNMATCHED. Explicit unknown-package language forces UNMATCHED. A confident match with nothing to apply is routed to review.
   - The top 20 candidates and a decision with a reason are stored.
3. **Decide**: planner confirm, reassign or reject (or Time Agent "yes"). Pending AUTO_MATCHED events are listed under "Awaiting confirmation". APPROVED and REJECTED are terminal, with one approval per event enforced by a unique index. Human decisions are appended, not overwritten.
4. **Update**: `apply_update()` enforces monotonic progress (never reopens or lowers; 409), then writes actuals, an audit row, the delay cause and execution memory, with a CPM snapshot before and after.
5. **CPM**: deterministic NetworkX forward and backward pass over stored FS/SS/FF/SF dependencies. With data date = today it forecasts from actuals and remaining work. Each snapshot records its data date; startup and schedule reads recompute when it has moved. At-risk means a late start, or a forecast finish after the planned finish with float under 2 days.
6. **Analytics and memory**: planned-vs-actual variance, productivity, delay causes, and execution-memory search.

CPM is project-controls mathematics, not AI. Terminology comes from `data/terminology_map.v1.yaml`, which is loaded at every startup.
