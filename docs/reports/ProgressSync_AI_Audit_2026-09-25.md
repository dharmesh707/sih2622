# ProgressSync AI (SIH26122): Final Audit Report

**Audit date:** 2026-09-25
**Audited revision:** `3b1ffc7` (`docs: add prototype technical handover`) on `main`
**Audit basis:** [docs/prompts/ProgressSync_AI_Claude_Code_Plugin_Setup_UPDATED.md](../prompts/ProgressSync_AI_Claude_Code_Plugin_Setup_UPDATED.md), sections 13–17
**Scope:** Audit only. No source, data, test or config files were changed. Every result below comes from commands, scripts or browser sessions run during this audit, unless it is marked *code inspection*.

---

## 1. Executive summary

The backend pipeline (ingest → extract → score → route → confirm → audit → CPM) **works end to end for the happy path**. The React/Vite frontend **builds and runs against the real backend**. The core safety rule holds in normal use: an uncertain match is never written to the schedule without a human action.

The project is **not yet demo-complete against the setup document's five verification scenarios**:

| Scenario (setup doc §14) | Result |
|---|---|
| A: Confident report → AUTO_MATCHED → confirmation → schedule update → audit → CPM | **Partial.** AUTO_MATCHED works, but the React UI has no way to confirm an AUTO_MATCHED event, so the schedule is never updated from the UI. |
| B: Ambiguous report → REVIEW_REQUIRED → candidate comparison → planner selection → update | **Partial.** The review and approval flow works, but the UI shows only the rank-1 candidate. Planners can't compare candidates or pick a different one. |
| C: Unknown activity → UNMATCHED → observation preserved → no fabricated activity_id | **Pass.** One caveat: the UI offers a one-click "Approve top candidate" on UNMATCHED events (see B-07). |
| D: Time Agent → clarification if required → same pipeline → schedule/audit update | **Partial.** It uses the same pipeline, but there is no clarification or multi-turn behaviour and the replies are canned. |
| E: Updated schedule → Gantt → critical-path impact → variance/analytics → institutional memory | **Partial / not met.** There is no Gantt. CPM impact is shown but can't change on actuals. "Variance" is only average progress. Institutional memory reports the wrong duration. |

**Most important new finding (missed by the 2026-09-22 handover):** `norm()` in [backend/app.py:239](../../backend/app.py) replaces **every letter `o` with the digit `0`** in all text. This silently breaks:

- terminology mapping for `spool`, `boltup`, `hydrotest`, `erection` and `CT103`
- discipline detection for civil (`foundation`, `concrete`) and rotating (`rotating`)
- `complete`/`completed` → 100% inference
- the `unknown package` / `unknown work package` wording signal

See B-01.

**Tests:** `pytest -q` gives **5 passed** once the MiniLM model is cached locally. On a clean machine it gives **3 failed, 2 passed**, because the model is loaded with `local_files_only=True` and nothing in the repo downloads it (B-03).

---

## 2. Plugin setup verification (setup doc §17 checklist)

| Checklist item | Status | Evidence |
|---|---|---|
| Node on PATH | ✅ | `node --version` → v24.19.0 |
| Ponytail installed | ✅ | `claude plugin list` → ponytail@ponytail 4.10.0, enabled, default mode |
| Chrome DevTools MCP installed | ✅ | `claude mcp list` → `chrome-devtools: npx -y chrome-devtools-mcp@latest ✔ Connected`. Installed through the doc's CLI fallback, not the marketplace plugin. |
| React plugin installed | ✅ | react@pleaseai 1.2.1, enabled |
| Vite plugin installed | ✅ | vite@pleaseai 1.2.1, enabled |
| Run Verify installed | ✅ | run-verify@pleaseai 0.1.0, enabled |
| `/plugin` shows expected plugins | ✅ | As above. The claude.ai-synced plugins `data`, `small-business` and `bigdata-com` are also loaded; they are outside the doc's recommended set (§8). |
| Chrome DevTools tools available | ✅ | Used for the browser verification in §5 |
| Excluded tooling (Supabase, mobile, XER, 3D) not installed | ✅ | Not present |
| PostgreSQL/database decision settled | ❌ Not settled | The code is SQLite-only. The README says the schema is "shaped for a PostgreSQL migration", but there is no migration or Postgres code. |
| Context document / final implementation prompt available | ⚠️ Partly | The handover docs exist (`FINAL_PROTOTYPE_TECHNICAL_HANDOVER.md`, `FINAL_PROTOTYPE_QUICK_START.md`). No "final implementation prompt" file was found in the repo. |
| Optional features don't block core workflow | ✅ | OCR/ASR/P6/XER/3D are absent and nothing depends on them |

---

## 3. Environment used

- Windows 11, Python 3.13.5, Node 24.19.0.
- No project venv existed (`.venv` is absent). A throwaway venv was created **outside the repo** at `%TEMP%\psv` and `pip install -r requirements.txt` was run there. Resolved versions: fastapi 0.141.1, sentence-transformers 6.1.0, torch 2.14.0, scikit-learn 1.9.1, networkx 3.7, pytest 9.1.1.
  - Note: the scratchpad location initially failed with a Windows long-path error during the torch install. Anyone installing into a deeply nested path on Windows may hit this.
- Browser checks used a temporary SQLite DB outside the repo (`PROGRESSSYNC_DB=%TEMP%\psv\live.db`). Backend: `uvicorn backend.app:app --port 8000`. Frontend: Vite dev server on 5173.
- Artifacts left in the repo, all gitignored: `frontend-react/node_modules/` and `frontend-react/dist/`. `git status` shows no tracked changes.

---

## 4. Automated tests and verification commands

### 4.1 Backend tests

| Run | Command | Result |
|---|---|---|
| Clean machine (no cached MiniLM) | `python -m pytest -q` | **3 failed, 2 passed.** `OSError: We couldn't connect to 'https://huggingface.co' to load the files, and couldn't find them in the cached files.` Failing: `test_report_match_candidates_and_explainability`, `test_review_confirm_writes_actual_and_audit`, `test_unmatched_is_preserved_and_agent_uses_same_pipeline`. |
| After one-time `SentenceTransformer('all-MiniLM-L6-v2')` download into `~/.cache/huggingface` | `python -m pytest -q` | **5 passed, 306 warnings in 13.95 s** |

Warnings: FastAPI `@app.on_event` deprecation, `datetime.utcnow()` deprecation, and a Starlette TestClient re-export warning.

**Coverage gaps (code inspection of [tests/test_pipeline.py](../../tests/test_pipeline.py)):**
- The five tests assert loosely. For example, the confident report may be `AUTO_MATCHED` **or** `REVIEW_REQUIRED`, and the unknown report may be `UNMATCHED` **or** `REVIEW_REQUIRED`.
- Nothing tests duplicate/conflicting confirmation, reject-after-approve, project isolation, a missing activity, a missing model, a dependency cycle, terminology mapping of `spool`, or the frontend.
- There are no frontend unit tests and no browser E2E tests.

### 4.2 Benchmark (`python scripts/run_benchmark.py`, run twice)

| Metric | This audit | Handover (2026-09-22) |
|---|---:|---:|
| Held-out cases | 9 | 9 |
| Auto-match precision | 100.0% | 100.0% |
| Silent errors | 0 | 0 |
| Auto-match rate | 88.9% | 88.9% |
| Review rate | 11.1% | 11.1% |
| Unmatched rate | 0.0% | 0.0% |
| Recall@5 | 100.0% | 100.0% |
| Median latency | **245.08 ms / 253.60 ms** | 47.74 ms |

The routing metrics reproduce exactly. Latency is about 5× higher on this machine. Latency depends on hardware and must not be quoted as a fixed number.

**Benchmark validity concerns (code inspection of [scripts/generate_corpus.py](../../scripts/generate_corpus.py) and [scripts/run_benchmark.py](../../scripts/run_benchmark.py)):**
1. Only **9 held-out cases**, and **none of them is an unknown/unmatched case**: unknowns are generated at `index % 10 == 0`, and held-out is indices 51–59. The UNMATCHED path is not benchmarked at all.
2. Each report copies its activity's description verbatim, including a unique number (e.g. "Safety inspection 154 …" → `HSE-L6-154`). That makes top-1 near-trivial, so the 100% figures say little about real field language.
3. The benchmark calls `score_candidate()` with `terms=[]`, so **terminology mapping is not exercised**. It also re-implements routing instead of calling `make_match()`, so the discipline filter and unknown-signal logic are not exercised either.
4. The `index % 6 == 2` "activity-code formatting" variant is a no-op, because report texts never contain the activity code.
5. Event dates are `date.today()` while `schedule.csv` dates are frozen at generation time. The temporal factor, and therefore the scores, drift with the calendar date of the run, so results are not strictly reproducible over time.
6. The held-out set is not used for tuning (no evidence of that was found), which is correct.

### 4.3 Reranker evaluation (`python scripts/evaluate_reranker.py`)

| | Baseline | Reranker |
|---|---:|---:|
| Top-1 | 100.0% | 100.0% |
| Auto-match rate | 88.9% | 100.0% |
| Silent errors | 0 | 0 |
| Median latency | 215.49 ms | **8.77 ms** |

The reranker latency number is **misleading**. Its timer starts *after* the baseline scoring that the reranker needs as input, so the "215 ms → 8.77 ms" comparison is not like-for-like. The reranker metrics artifact reports validation ROC-AUC 1.0 on 800/220 synthetic candidate rows. That is not evidence of real-world performance. The reranker is **disabled by default** (`/api/v1/ml/status` → `reranker_enabled: false`).

### 4.4 Frontend build

| Command (from `frontend-react/`) | Result |
|---|---|
| `npm ci` | OK. One warning: `esbuild` postinstall not covered by `allowScripts`. |
| `npm run build` | **OK.** Vite 7.3.6, 41 modules, JS 243.95 kB (75.45 kB gzip), built in 4.80 s |
| `npm audit` | 0 vulnerabilities |

---

## 5. Browser verification (Chrome DevTools MCP, React UI at http://127.0.0.1:5173)

The backend was fresh (seeded 35-activity demo schedule). All API calls in the session returned **200**. The console showed no JavaScript errors. There was one 404, which matches `/favicon.ico` (verified with curl: 404), and an accessibility notice: "A form field element should have an id or name attribute" (3 fields).

| Step | Input | Observed |
|---|---|---|
| A1 | High-confidence sample `Piping crew completed spool XX102 at rack 3, 100%.` | `AUTO_MATCHED`, "Candidate activity #2", top 0.869, runner-up 0.656, margin 0.213. **No confirm button is shown for AUTO_MATCHED.** The activity code/description and evidence are not displayed, only `#2`. |
| A2 | Metric strip after the reports | **"Last latency" stays `-- ms`** and **"Reports processed" stays 0** (B-10, B-11) |
| B1 | Ambiguous sample `Piping crew working at rack 3, spool aligned, 50%.` | `REVIEW_REQUIRED`, top 0.642, runner-up 0.631, margin 0.011 |
| D1 | Time Agent `XX102 started at 9.` | Canned reply "I found multiple plausible activities. Please review the evidence." `REVIEW_REQUIRED`, margin 0.314. **No clarification question**, e.g. "Which XX102?". |
| C1 | `ZZ-999 unknown activity at offshore platform, 20%.` | `UNMATCHED`, "Observation preserved without a schedule link", `activity_id` null ✅ |
| Review queue | – | 3 cards (events 4, 3, 2). Each shows ID/lexical/semantic/context bars, top/runner-up/margin and the **rank-1 candidate only**. Event 2 shows "Mapped terms: rack 3 → R03"; **`spool → piping segment` is missing** (B-01). The UNMATCHED ZZ-999 card offers **"Approve top candidate" → `CIV-L5-008 Foundation and concrete works`** (B-07). |
| B2 | Approve event 2 | Post-confirm panel: progress 0% → 50%, status not_started → in_progress, "PATH STABLE", project finish 156.0 → 156.0, nothing entered or left the critical path. There was no confirmation dialog. |
| Schedule | – | A table (not a Gantt). All 35 activities show 0.0d float / critical, because the seed data is a single chain. Planned dates start 12 days before today, yet everything shows `not_started` and nothing is flagged at-risk. Actual finish is not shown. |
| Analytics | – | Discipline progress: piping 10%, others 0%. "WBS variance" lists 35 packages with average progress, and there is **no variance against plan**. Delay causes: "No delay causes logged yet." |
| Audit + memory | – | The audit row for activity #30 shows old/new JSON, evidence text, actor `planner`, score 0.64 ✅. Institutional memory shows "No historical executions yet" (correct, since nothing is 100% complete). The terminology map lists 10 terms. |
| Static UI | `GET http://127.0.0.1:8000/` | 200. The static UI is served. It was not exercised further. |

---

## 6. Bugs (verified)

Severity: **High** = breaks a core SIH requirement or data integrity; **Medium** = wrong output or unsafe edge case; **Low** = cosmetic or misleading.

| ID | Severity | Bug | Evidence / repro |
|---|---|---|---|
| B-01 | **High** | `norm()` converts every `o` to `0`. The line `text.replace("1o","10").replace("o","0")` ([backend/app.py:239](../../backend/app.py)) was presumably meant for OCR digit fixes but applies to all text. Consequences: (a) the terminology terms `spool`, `boltup`, `hydrotest`, `erection` never match, and `CT103` never matches because the field text is lower-cased and split to `ct 103`; (b) `foundation`, `concrete` and `rotating` never set a discipline; (c) `complete/completed/finished` without `%` never sets progress 100; (d) `unknown package` / `unknown work package` never triggers the explicit-unknown signal (only the `ZZ-nnn` regex works). | `norm('spool completed foundation unknown')` → `sp00l c0mpleted f0undati0n unkn0wn`. `Foundation concrete poured at Area A, 40%.` → discipline `None`, decision `UNMATCHED`. `Rotating crew aligned CT103 …` → discipline `None`. In the browser, the spool report's evidence shows only `rack 3 → R03`. `Cable pull done on rack 3` maps correctly (no `o` in the term). |
| B-02 | **High** | Reject-after-approve reopens an approved event and allows a **second schedule write and second audit row**. `reject()` updates *all* decisions for the event to `REJECTED`, including the `APPROVED` one, without rolling back the schedule. `confirm()` only blocks when the latest decision is `APPROVED`. | Probe: confirm → 200, reject → 200, confirm → 200; **2 audit rows** for one event; the event status says `REJECTED` while the activity keeps the approved update. [backend/app.py:863-866](../../backend/app.py), [843](../../backend/app.py) |
| B-03 | **High** (setup) | The MiniLM model is mandatory and offline-only (`local_files_only=True`, [backend/app.py:121-124](../../backend/app.py)), and nothing in the repo or README downloads it. On a clean machine every report request raises a 500 and 3/5 tests fail. The README and `docs/decisions.md` still claim a "deterministic proxy" fallback that doesn't exist. | §4.1 clean-machine run |
| B-04 | **High** | Project scoping is hardcoded to 1. `make_match()` only scores `project_id=1` ([app.py:473](../../backend/app.py)), and `confirm()` always passes project 1 ([app.py:856](../../backend/app.py)). Confirm doesn't check that the activity belongs to the event's project. | Probe: imported 5 rows into project 2, then posted a report with `project_id: 2` → **zero candidates from project 2**. Confirming a project-2 activity wrote an audit row with `project_id = 1`. |
| B-05 | Medium | A report with "completed" but no `%` is AUTO_MATCHED with `progress = None`. Confirming it writes a no-op update (old == new, still `not_started`) plus an "approved" audit row. | Probe: `Piping crew completed spool XX102 at rack 3.` → `AUTO_MATCHED`, progress `None`; confirm → old/new both `0.0 / not_started`. Root cause is B-01 plus there being no guard for `progress is None`. |
| B-06 | Medium | Confirming with a nonexistent `activity_id` crashes with an unhandled `TypeError` (HTTP 500) instead of returning 404. `apply_update()` also runs a "pre-update" CPM recompute before it fails. | Probe: `POST /events/{id}/confirm {"activity_id": 999999}` → `TypeError: 'NoneType' object is not subscriptable` ([app.py:732-734](../../backend/app.py)) |
| B-07 | Medium | The review UI's only positive action is "Approve top candidate", even for **UNMATCHED** events. One click links an unknown observation to an unrelated activity (ZZ-999 offshore → `CIV-L5-008 Foundation`, score 0.327). Only rank #1 is shown, with no runner-up, no list and no alternative selection. This undercuts the "never force an uncertain match" rule in the UI. | Browser §5, [ReviewView.jsx:41,99,121](../../frontend-react/src/views/ReviewView.jsx) |
| B-08 | Medium | `reject` on a nonexistent event returns 200 `{"decision":"REJECTED"}`. | Probe: `POST /events/987654/reject` → 200 ([app.py:863-866](../../backend/app.py)) |
| B-09 | Medium | A dependency cycle makes `recompute` raise an unhandled `ValueError` (HTTP 500). Schedule import calls `recompute()` too, so a cyclic graph makes import fail after rows are committed. | Probe: inserted a back-edge → `ValueError: Dependency graph contains a cycle` ([app.py:696-697](../../backend/app.py)) |
| B-10 | Low | The "Last latency" metric never displays. `submitReport` sets `latency`, then `refresh()` calls `setMetrics({...})` without `latency` and overwrites it. | Browser: `-- ms` after 3 submissions. [IngestView.jsx:38 vs 56](../../frontend-react/src/views/IngestView.jsx) |
| B-11 | Low | "Reports processed" counts distinct `event_id`s in the **audit log** (confirmed updates only), not processed reports. | Browser: 0 after 3 reports and 1 agent message; [App.jsx:25](../../frontend-react/src/App.jsx), [IngestView.jsx:41](../../frontend-react/src/views/IngestView.jsx) |
| B-12 | Low | Institutional memory returns `planned_duration` as `actual_duration`, and the UI labels it "actual duration … days". | Probe P8: equal for all rows. [app.py:926](../../backend/app.py) (also noted in the handover) |
| B-13 | Low | Productivity analytics names an average of planned duration `actual_duration`. Analytics and memory queries ignore `project_id` and aggregate every project. | [app.py:912-926](../../backend/app.py) (code inspection) |
| B-14 | Low | Spurious ID signal: any activity-code token longer than 2 characters found in the report text gives `score_id = 0.82`. For example, `PIP` matches "**pip**ing", so every piping activity gets 0.82 for any report that says "piping". | Browser: the ambiguous report shows ID 0.82 against `PIP-L5-030`. [app.py:371-376](../../backend/app.py) |
| B-15 | Low | The Schedule view silently shows only the first 50 activities (`slice(0, 50)`). Imported schedules larger than that, e.g. the 280-row benchmark schedule, are truncated with no indication. | [ScheduleView.jsx:49](../../frontend-react/src/views/ScheduleView.jsx) (code inspection) |
| B-16 | Low | The `make_match()` fallback for "no candidates" calls `score_candidate(event, event, …)`. The event dict has no `activity_code`/`description`/`id` keys, so it would raise `KeyError`. It is only reachable when no activity of the extracted discipline exists in project 1. | [app.py:499-506](../../backend/app.py) (code inspection; not triggered with seed data) |
| B-17 | Low | Documentation drift: README/`docs/demo.md`/`.env.example` advertise `DEMO_MODE` (never read), a semantic proxy fallback (doesn't exist), and "The browser is a small static frontend" (React is now the intended UI). `.env.example` omits `PROGRESSSYNC_USE_RERANKER`. `requirements.txt` is unpinned and doesn't list `scikit-learn`, which the reranker pickle needs; it currently arrives only as a transitive dependency of sentence-transformers. The root `package-lock.json` has no `package.json` (empty `packages: {}`). | Code/doc inspection |

---

## 7. Incomplete features vs. setup doc §13–16

| Requirement | State | Detail |
|---|---|---|
| React/Vite integrated with FastAPI using real backend data | ✅ Mostly | Every view calls live `/api/v1` endpoints, with no mocked success states. React needs a separate Vite server. FastAPI `/` still serves the older static UI, and no single supported frontend has been decided. |
| AUTO_MATCHED confirmation from the UI | ❌ Missing | The React UI has no confirm path for AUTO_MATCHED events. The backend `/confirm` works for them via the API. |
| Candidate comparison and planner selection | ❌ Missing | Only rank #1 is shown. The backend already returns up to 20 ranked candidates with evidence. |
| Gantt | ❌ Missing | The Schedule view is a table; there is no timeline or bar rendering. |
| CPM impact | ⚠️ Shallow | CPM uses planned durations only, so confirming actuals never changes finish or float (probe: 156.0 → 156.0 even after a 100% confirm). Imported schedules get no dependency edges (`parent_activity` is ignored; probe: 0 edges), so imported activities are not networked. |
| Variance analytics | ⚠️ Mislabelled | "WBS variance" is average progress per WBS path. No planned-vs-actual variance is computed. |
| At-risk flag | ❌ Not calculated | The `at_risk` column is always 0, even though seed activities are past their planned start with 0% progress. |
| Delay causes | ❌ No write path | The table and read endpoint exist; nothing writes to them. |
| Institutional memory | ⚠️ Wrong data | Uses planned duration as actual (B-12). |
| Time Agent clarification / multi-turn | ❌ Missing | `session_id` is ignored and replies are canned. A follow-up like "Rack 3." is processed as a new, unrelated report (probe → `UNMATCHED`). |
| Time Agent voice | ⚠️ Browser-only | Web Speech API in the report panel only. It was not tested (no microphone in the automated browser). |
| Extracted time used | ❌ | `time_text` is captured (e.g. "9") but not used. `event_timestamp` is always today's date. |
| Schedule import | ⚠️ Partial | CSV/XLSX validation works. `contractor` and `resource` are dropped (probe: `None`); `parent_activity` and dependencies are ignored. |
| YAML terminology source | ❌ Not used | `data/terminology_map.v1.yaml` is not read; startup inserts a hardcoded list. |
| Auditability | ⚠️ | Old/new values, evidence, actor and score are recorded. Immutability is by convention only, and B-02 allows a double write. The actor is a free-text string with no authentication. |
| PostgreSQL | ❌ Not started | SQLite only. There are no FKs, indexes or migrations (per the schema in [app.py:148-167](../../backend/app.py)). |
| Demo DB / release environment cleanup | ❌ Not done | There is no reset script and no pinned requirements. The model is not bundled (B-03). |

---

## 8. What was NOT verified

- **Voice input** (Web Speech API): needs a real microphone and user permission.
- **Schedule upload through the browser UI**: verified through the API/TestClient (CSV into project 2 and the XLSX test), not by clicking the file input.
- **Reranker enabled end to end in the live app** (`PROGRESSSYNC_USE_RERANKER=true`): only evaluated offline via `scripts/evaluate_reranker.py`.
- **Static frontend (`frontend/`) flows**: only confirmed that `/` returns 200.
- **The retraining pipeline** (`generate_corpus.py`, `build_reranker_dataset.py`, `train_reranker.py`): deliberately **not run**, because it would overwrite tracked held-out and training files.
- **`scripts/demo_flow.py`**: not run. It would write to the default `data/progresssync.db`.
- **Performance at scale**: scoring is O(activities) per report with MiniLM encoding. It was not measured beyond 280 activities.
- **Pickle compatibility across scikit-learn versions**: the artifact loaded under scikit-learn 1.9.1, but the training version isn't recorded.
- **Security** (no auth, `CORS *`, unauthenticated write endpoints): noted from code; no penetration testing was done.
- **The PDF master development document**: not reviewed against the code.

---

## 9. Recommended fix order (not implemented)

Following the setup doc's rules (incremental, keep the matcher, add a test per change):

1. **B-01** Restrict the `o→0` substitution to digit contexts only (e.g. inside alphanumeric identifiers), then add tests for `spool` mapping, civil discipline detection and `completed` → 100. Re-run the benchmark and report before/after numbers honestly.
2. **B-02 / B-06 / B-08** Make reject refuse approved events (or define reversal semantics). Return 404 for a missing event or activity. Add tests for duplicate and reject-then-confirm cases.
3. **B-03** Document or script the one-time MiniLM download (or bundle the model), and remove the stale "proxy fallback" claims.
4. **Scenario A/B UI:** add a confirm action for AUTO_MATCHED, show the top-N candidates with a selection control, and require an explicit choice (not "approve top") for UNMATCHED.
5. **B-04** Propagate `project_id` through matching and confirm, and validate ownership.
6. Gantt view, at-risk calculation, true variance, and actual-duration memory, in that order, following the handover roadmap.
7. Expand the held-out benchmark to include unknown cases and field-style paraphrases, and fix report dates so runs are reproducible.

---

## 10. Commands to reproduce this audit

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q                      # clean machine: expect 3 failed (no local MiniLM)
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
python -m pytest -q                      # expect 5 passed
python scripts/run_benchmark.py
python scripts/evaluate_reranker.py
cd frontend-react; npm ci; npm run build
# live check: $env:PROGRESSSYNC_DB="$env:TEMP\ps.db"; uvicorn backend.app:app  +  (frontend-react) npm run dev
```
