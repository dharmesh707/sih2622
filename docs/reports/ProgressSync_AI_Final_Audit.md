# ProgressSync AI (SIH26122): Final Audit and Independent Review

**Audit date:** 2026-09-26
**Audited state:** `main` @ `3b1ffc7` **plus uncommitted working-tree changes** (26 modified or deleted tracked files, about +1387/−528 lines, and 20+ new files). The next-phase work has not been committed.
**Basis:** [docs/prompts/ProgressSync_Next_Phase_SINGLE_Claude_Pro_Prompt.md](../prompts/ProgressSync_Next_Phase_SINGLE_Claude_Pro_Prompt.md), the 25 Sep audit (kept as [ProgressSync_AI_Audit_2026-09-25.md](ProgressSync_AI_Audit_2026-09-25.md)), [PROGRESS.md](../../PROGRESS.md), and the current code.
**Mode:** read-only review. No source, test, data or config file was changed. See §11 for the files this audit wrote.

> **Independence caveat:** the same agent (Claude Code) that implemented the next phase also performed this review. To offset that, every claim below is backed by a command, probe or browser action that was re-executed on 2026-09-26, and new probes deliberately targeted areas the implementation did not test. The main developer should still do a human review before submission.

---

## 1. Verdict

The project is **demo-ready for the five SIH scenarios (A–E)**, which were re-verified end to end in a browser. Backend tests, frontend build, dependency pinning and the frozen benchmark all pass.

It is **not yet safe for unsupervised real-site use**. Two data-integrity defects were found that the implementation's tests did not cover:

1. **Negated field language is read as progress (High).** "not completed yet" and "will be completed tomorrow" are extracted as **100%** and AUTO_MATCHED; one click in the UI then marks the activity **complete**. "not started" writes an **actual start**.
2. **A lower-progress report silently regresses a completed activity (High).** Status goes back to `in_progress` while `actual_finish` is kept, which is an inconsistent state.

**The P1 extraction issue (bare line numbers and single-letter tags) is NOT resolved** (§3).

---

## 2. Checks actually run (2026-09-26)

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest -q` | **64 passed, 1 warning** (Starlette TestClient re-export warning from inside FastAPI) |
| Pinned install (run in the previous session, re-confirmed from its log) | fresh venv → `pip install -r requirements.txt` → `pytest` | install exit 0, **64 passed** |
| Frontend clean install + build | `cd frontend-react && rm -rf node_modules dist && npm ci && npm run build` | OK, JS 259.47 kB (79.61 kB gzip). One npm `allow-scripts` warning for esbuild's postinstall |
| npm audit | `npm audit` | **0 vulnerabilities** |
| Benchmark, dev | `python scripts/run_benchmark.py --split dev` | 56 cases, auto precision 100% (15), **0 silent errors**, top-1 83.7%, R@5 98.0% |
| Benchmark, frozen held-out | `python scripts/run_benchmark.py` | 84 cases, auto precision **100% (13)**, **0 silent errors**, AUTO/REVIEW/UNM 15.5/67.9/16.7%, top-1 **76.2%**, R@5 92.1%, 13/13 unknown → UNMATCHED, 0 cross-project candidates, median 61.7 ms. Identical to PROGRESS.md except latency |
| Benchmark, reranker on | `python scripts/run_benchmark.py --reranker` | auto precision 88.9% (54), **6 silent errors** (abbreviation 3, wrong discipline 2, synonym 1). Reproduces PROGRESS.md |
| Manifest / freeze | code inspection of `run_benchmark.py` | SHA-256 check present; not tamper-tested (that would require modifying frozen files) |
| Legacy scripts | `scripts/demo_flow.py` (temp DB), `scripts/evaluate_reranker.py` | Both run. The legacy reranker still scores 100%/0 silent on the **old** corpus, which confirms that corpus is too easy |
| Targeted probes | throwaway DB, TestClient (§4) | See findings F-01 to F-12 |
| Browser E2E | Chrome DevTools MCP against `uvicorn` :8000 serving the built UI, throwaway DB | Scenarios A–E pass; defects F-01, F-03 and F-09 reproduced in the UI (§5) |

The ML status endpoint reported the pinned MiniLM revision `1110a243…` as available and the reranker as disabled.

---

## 3. P1: line-number and single-letter-tag recognition — **NOT RESOLVED**

`extract_event()` still uses `\b(?:[A-Z]{2,5}[- ]?\d{2,4}|[A-Z]{1,3}\d{3,4})\b` ([backend/app.py:360-362](../../backend/app.py)). Probe results:

| Report text | Extracted identifiers |
|---|---|
| `Line 2104 piping segment erected at R01, 100%.` | `[]` |
| `Ln 2111 pip seg erctd R02 100%` | `[]` |
| `Install pump P-301, 50%.` | `[]` |
| `Pump P 305 aligned, 100%.` | `[]` |
| `Erect vessel V-201, 60%.` | `[]` |
| `Inst pmp P303 80%` | `['P303']` (only because there is no hyphen) |
| `Calibrate transmitter PT-101, 100%.` | `['PT-101']` (two-letter tags work) |

**Partial mitigation only.** The B-14 fix lets a number count as ID evidence when it also appears as a whole token in the **activity code** (e.g. `PIP-2104`). When codes do not embed the tag or line number, which is typical of real P6 codes, there is no ID evidence at all. On a schedule whose codes lack the tag digits (`ROT-A`, `ROT-B` for pumps P-301 and P-302):

| Report | Decision | Top-2 (`score_id`, fused) |
|---|---|---|
| `Install pump P-301, 50%.` | REVIEW_REQUIRED | ROT-A (0.0, 0.609), ROT-B (0.0, 0.567) |
| `Erect vessel V-201, 60%.` | REVIEW_REQUIRED | STA-A (0.0, 0.693), STA-B (0.0, 0.661) |
| `Line 2104 piping segment erected at R01, 100%.` | REVIEW_REQUIRED | PIP-A (0.0, 0.665), PIP-B (0.0, 0.642) |

The outcome is safe (review, not a wrong AUTO), but the tag or line number that uniquely identifies the activity is ignored, and the margin is only about 0.03. In the benchmark this shows up as abbreviation top-1 72.7% and near-duplicate top-1 0% (held-out).

---

## 4. Findings

Severity: **High** means it can write wrong schedule data or break a core SIH claim. **Medium** means a wrong or missing workflow, or a real integrity gap. **Low** is minor or cosmetic.

| ID | Sev. | Finding | Evidence (re-run 2026-09-26) | Location |
|---|---|---|---|---|
| F-01 | **High** | **Negation ignored in progress/start inference.** `\b(complete\|completed\|finished)\b` and `\bstart(s\|ed\|ing)?\b` match inside "not completed", "will be completed tomorrow" and "not started". | `Spool XX102 at rack 3 not completed yet.` → progress **100**, AUTO_MATCHED. Confirming it wrote `status: complete, actual_finish: today`. `… not started due to rain.` → confirm wrote `actual_start: today, in_progress`. **Reproduced in the browser:** `Piping crew: spool XX103 at rack 3 not completed yet.` shows "progress 100%" and a one-click **"Confirm update to PIP-L5-009"** | [app.py:401](../../backend/app.py), [:908](../../backend/app.py), [:966-970](../../backend/app.py) |
| F-02 | **High** | **Regression of a completed activity with inconsistent state.** A lower-% report confirmed against a complete activity overwrites progress and status but keeps `actual_finish`. | Activity at 100%/complete with actual_finish set; confirmed "…working, 30%" → new `{percent_complete: 30, status: in_progress, actual_finish: 2026-09-26}`. There is no warning and no guard | [app.py:967-970](../../backend/app.py) (`apply_update`) |
| F-03 | Medium | **Unconfirmed AUTO_MATCHED events are orphaned.** The review queue lists only REVIEW_REQUIRED/UNMATCHED. An AUTO_MATCHED report whose Ingest card is navigated away from (or a Time Agent session abandoned at "Confirm?") cannot be found or confirmed in the UI. | API probe: AUTO_MATCHED event not in `/review-queue`. Browser: event #2 (AUTO, unconfirmed) absent from the queue, which showed only #3 and #4 | [app.py:1114-1121](../../backend/app.py) |
| F-04 | Medium | **P1 extraction gap** (§3) | see §3 | [app.py:360-362](../../backend/app.py) |
| F-05 | Medium | **Forecast CPM and at-risk flags go stale.** They are recomputed only on confirm, import or manual recompute, or on first seed. A `GET` does not recompute, so after midnight (the data date moves) the Gantt and at-risk list show yesterday's forecast until someone clicks "Recompute CPM". | Probe: `GET /projects/1/activities` created no new snapshot. `init_db` recomputes only when seeding | [app.py:211-225](../../backend/app.py), [:873](../../backend/app.py) |
| F-06 | Medium | **No authentication or authorization; CORS `*`.** Any caller can import schedules, create projects implicitly, confirm or reject, and write delay causes. `actor` is free text. Accepted limitation for a prototype, but it is a blocker for any shared deployment. | Import to `project_id=999` auto-created the project and inserted 6 rows | [app.py:1037](../../backend/app.py), import endpoint |
| F-07 | Medium | **Legacy reranker is unsafe if enabled** (6 silent errors on held-out). Mitigated: off by default, and the README warns. There is no hard guard. | benchmark `--reranker` | `PROGRESSSYNC_USE_RERANKER` |
| F-08 | Low | **`report_date` is not bounded.** A future date (e.g. 2099-01-01) is accepted and would become actual start/finish dates on confirmation. | `POST /reports {report_date: 2099-01-01}` → 200 | `ReportIn` |
| F-09 | Low | **Project selector hidden on narrow screens, and the mobile layout overflows.** The selector lives inside `.status`, which the ≤850 px media query hides. At 390 px the layout width grew to 447 px and content is clipped on the right. | Browser emulation 390×844: selector not visible; `innerWidth` 447 | [styles.css:39](../../frontend-react/src/styles.css) |
| F-10 | Low | **Time Agent session reuse across projects** replaces the session state but keeps the old project's messages in the same transcript. Session ids are unauthenticated bearer strings. | Session from project 1 reused with `project_id: 7` → state reset, transcript holds 4 messages spanning both projects | `agent()` [app.py:1352+](../../backend/app.py) |
| F-11 | Low | **Time Agent candidate pick uses a substring test.** `activity_code.lower() in text.lower()`, so a very short code (e.g. `A1`) could be "picked" by unrelated text. Not triggered with the demo codes. | code inspection | [app.py:1372](../../backend/app.py) |
| F-12 | Low | **Mixed time bases.** Audit and decision timestamps are UTC (`…Z`) while actual dates and the CPM data date use the server's local date. At 02:00 IST an audit row reads the previous day. Labelled "UTC" in the UI; the weekly delay trend buckets by UTC date. | audit `2026-09-25T20:49:26Z` vs local `2026-09-26` | `now()` vs `date.today()` |
| F-13 | Low | **Completed activities are not down-ranked in matching.** A new report can be suggested against an already-finished activity (seen in the ambiguous demo case). Combined with F-02 this is how regressions happen. | E2E scenario B top-1 was the completed PIP-L5-002 in the prior session | `make_match` |
| F-14 | Low | **`project_id=1` defaults remain** in `ReportIn`/`AgentIn`, the seed and the UI's initial project. They are defaults, not hardcoded behaviour: project scoping itself is correct and tested. | code inspection | [app.py:1005](../../backend/app.py), [:1024](../../backend/app.py) |
| F-15 | Low | **Local demo DB is not clean.** `data/progresssync.db` (gitignored) still holds data from the previous E2E session: 4 audit rows, 5 reports, 1 delay cause, 1 agent session. | read-only SQLite query | run `python scripts/reset_demo_db.py` before the demo |
| F-16 | Low | **Accessibility notice.** 22 form fields have no `id`/`name` (Chrome issue panel); inputs do have `aria-label`s. | console `issue` message | React inputs |

### Verified as fixed or working (no action needed)

- **Concurrency:** 4 simultaneous confirms of one event gave statuses `[200, 409, 409, 409]` and exactly **1** audit row (partial unique index plus state check).
- **The 25 Sep audit defects:**
  - B-01 `norm()`, B-02 reject-after-approve, B-03 model provisioning, B-04 project scoping: fixed.
  - B-05 no-progress confirm: fixed (422). B-06/B-08 missing entities: fixed (404). B-09 cycle: fixed (409).
  - B-10/B-11 metrics, B-12/B-13 analytics: fixed. B-14 code-prefix ID: fixed. B-15 50-row limit: fixed (Gantt shows all rows). B-16 fallback: fixed. B-17 docs: fixed.
  - Each is covered by tests in `tests/test_*.py`.
- **Next-phase prompt items 1–18 and 20** are implemented and exercised. **Item 19** (frontend/browser E2E suite) is only partly met: E2E is manual through the MCP, and no automated browser suite is committed.
- **Security spot checks:** SQL is parameterized (the only f-string SQL uses internal constants). React escapes report text, so no HTML injection was seen. `/assets` is served by Starlette `StaticFiles`. The upload size limit (10 MB) is enforced before parsing.

---

## 5. Browser E2E (re-run 2026-09-26)

Setup: `uvicorn backend.app:app --port 8000` with `PROGRESSSYNC_DB` on a throwaway file, and the UI built by `npm run build` and served by FastAPI. Actions were real clicks and form input in Chrome, with results read back from the DOM.

| Scenario | Steps | Result |
|---|---|---|
| **A** Confident | high-confidence example → Process → Confirm | AUTO_MATCHED PIP-L5-002 (0.965, margin 0.531, `spool → piping segment, rack 3 → R03`). 0% → 100%, complete, audit #1 `approved`, CPM panel shown. **Pass** |
| F-01 in UI | `Piping crew: spool XX103 at rack 3 not completed yet.` | AUTO_MATCHED, "progress 100%", one-click confirm offered. **Defect reproduced** (not clicked) |
| **B** Ambiguous | ambiguous example → Review → select rank 2 → Reassign | REVIEW_REQUIRED (0.451, "top score 0.451 below 0.82") → "Reassign to PIP-L5-030" → `reassigned`, 0 → 50%. **Pass** |
| **C** Unknown | unknown example → Review | UNMATCHED ("report explicitly names an unknown work package"). The button reads "Select an activity" and is disabled; observation preserved. **Pass** |
| F-03 in UI | Review queue after leaving the XX103 AUTO event unconfirmed | Queue shows only #4 and #3; AUTO event #2 not reachable. **Defect reproduced** |
| **D** Time Agent | `XX104 started at 9.` → `Rack 3.` → `yes` | "Where is this work? My best guess is PIP-L5-016 … at R03" → same event #5 re-matched, AUTO 0.879 → "Recorded on PIP-L5-016 … actual start 2026-09-26, audit #3". **Pass** |
| **E** Schedule intelligence | `Foundation concrete poured at Area A, 40%.` → Review → confirm CIV-L5-008 with delay cause `weather` → Schedule / Analytics / Audit+memory | Forecast finish **2026-10-30 → 2026-10-27 (−3.4d)**, float PIP-L5-016 17.0→13.6d and PIP-L5-030 28.0→24.6d, at-risk list emptied. Gantt: 35 rows, 48 dependencies, completed CIV-L5-001 float "—". Analytics: 2 completed / 5 started, delay "weather ×1, 2026-W39". Memory: 5 rows, actual duration "n/a" until finished. **Pass** |
| Health | Network and console | 58 API requests, **0 non-200**. Console: no errors or warnings; one accessibility issue (F-16) |
| Mobile | 390×844 emulation | F-09 reproduced |

---

## 6. Data-integrity assessment

| Property | Status |
|---|---|
| Nothing is written to the schedule without a human confirmation | ✅ Holds (AUTO also requires Confirm) |
| One approval per event; approved/rejected are terminal | ✅ Enforced by DB index plus code; race-tested |
| Audit old/new values match the actual write | ✅ |
| Extracted progress reflects what the text says | ❌ F-01 (negation) |
| Activity state stays internally consistent | ❌ F-02 (in_progress with actual_finish; progress regression) |
| Every pending system decision is reachable by a planner | ❌ F-03 (orphan AUTO_MATCHED) |
| Forecast and at-risk reflect today's data date | ⚠️ F-05 (stale until the next write or recompute) |
| Project isolation | ✅ Matching, confirm, audit, analytics, memory and queue are project-scoped; 0 cross-project candidates in the benchmark |
| Referential integrity | ⚠️ SQLite without declared foreign keys (PostgreSQL explicitly out of scope) |

---

## 7. Not verified

- **Voice input** (browser Web Speech): needs a real microphone.
- **Schedule upload through the browser file picker.** Import is verified through API tests (CSV, XLSX, dependency files, cycle rejection).
- **Benchmark tamper refusal:** code-inspected only; testing it would mean modifying frozen files.
- **Clean-machine model provisioning:** not re-run in this session. It was run in the previous session during Phase 2 (the 503 and the pytest message, then the provision script, then the 28 tests that existed at that point passing). The later fresh-venv install used an already-populated model cache.
- **Performance beyond about 100 activities per project**, and concurrency beyond the 4-request confirm race.
- **Pickle and scikit-learn version compatibility** of the reranker artifact beyond 1.9.1.
- **The PDF master development document** against the implementation.
- **Automated browser regression:** none exists (prompt item 19 is only partly met).

---

## 8. Limitations of this audit

- Reviewer and implementer are the same agent (see the caveat at the top).
- The benchmark is synthetic (140 cases) and small; its numbers are not production accuracy.
- E2E used a single browser (Chrome) at desktop width plus one phone-width emulation.
- Findings reflect uncommitted working-tree code; any later change invalidates line references.

---

## 9. Recommended fix order (not applied)

1. **F-01:** handle negation and future tense before inferring progress or a start (e.g. `not|n't|yet to|will be|pending` near complete/start). Such reports should produce `progress = None` and fall under the existing 422/review path. Add regression tests using the probe sentences above.
2. **F-02 + F-13:** in `apply_update`, refuse or require explicit override when new progress is below current progress, or when the activity is complete. Clear `actual_finish` consistently if a reopen is allowed. Down-rank or flag completed activities in the candidate list.
3. **F-03:** show pending AUTO_MATCHED events (e.g. an "Awaiting confirmation" section in the Review queue, or include them in `/review-queue` with their decision).
4. **F-04 (P1):** extend identifier extraction to single-letter tags (`[A-Z]-?\d{3,4}`) and bare line numbers after `line|ln|L-`, matched against description tokens as well as codes. Validate on the **dev** split, then run the frozen held-out once.
5. **F-05:** recompute on startup, and when the data date has changed since the last snapshot (e.g. check on `GET /activities`).
6. **F-08, F-09, F-10, F-11, F-15** as small follow-ups. **F-06** (auth) before any shared deployment.
7. Commit the work on a branch and add an automated browser smoke test (item 19).

---

## 10. Reproduce

```powershell
python -m pytest -q
python scripts/run_benchmark.py; python scripts/run_benchmark.py --split dev; python scripts/run_benchmark.py --reranker
cd frontend-react; npm ci; npm run build; npm audit; cd ..
$env:PROGRESSSYNC_DB="$env:TEMP\audit.db"; uvicorn backend.app:app --port 8000   # then scenarios A–E per docs/demo.md
# F-01 repro: POST /api/v1/reports {"text":"Spool XX102 at rack 3 not completed yet."} → progress 100, AUTO_MATCHED
```

## 11. Files written by this audit

- `docs/reports/ProgressSync_AI_Final_Audit.md`: this report. It replaces the untracked 25 Sep version.
- `docs/reports/ProgressSync_AI_Audit_2026-09-25.md`: an unchanged copy of the previous audit, preserved before replacement.
- `benchmark/v2/results/{dev,held_out,held_out_reranker}.json`: regenerated by `run_benchmark.py` as a normal side effect. The metrics are identical to the previous run; only latencies differ.
- `frontend-react/node_modules` and `frontend-react/dist`: reinstalled and rebuilt (gitignored).

No source, test, data or configuration file was modified, and nothing was committed or pushed.
