# Demo script

Setup (once): see the README. Then:

```powershell
git checkout <evaluator commit SHA>      # always demo from the recorded commit, never a dirty tree
python scripts/reset_demo_db.py          # clean seeded database (stop the backend first)
cd frontend-react; npm ci; npm run build; cd ..
uvicorn backend.app:app                  # UI and API on http://127.0.0.1:8000; reranker stays off
```

To demo on a throwaway database instead, set `$env:PROGRESSSYNC_DB="$env:TEMP\progresssync_sih_final.db"` before both the reset and `uvicorn`.

The seed project "OIL Demo Project" has 35 activities in 5 packages with 48 FS links. It started 3 days ago, and CIV-L5-001 finished one day late, so the demo starts with a small slip on the critical path.

**A — Confident report.** In Ingest, load the high-confidence example `Piping crew completed spool XX102 at rack 3, 100%.` → AUTO_MATCHED PIP-L5-002, with the reason, score components and `spool → piping segment`, `rack 3 → R03` evidence. Click **Confirm** to see the schedule change, the audit row and the CPM impact. If you leave Ingest without confirming, the event waits under **Awaiting confirmation** in the Review queue.

**B — Ambiguous report.** Load the ambiguous example `Pump CT103 installed at Unit 2, 50%.` → REVIEW_REQUIRED ("margin 0.000 to runner-up"), because five seeded pump activities carry tag CT-103. In the Review queue, compare the top 5 candidates, select one other than rank 1, add a comment, and **Reassign**. The audit row records `reassigned`.

The older spool example `Piping crew working at rack 3, spool aligned, 50%.` has no identifier. Once scenario A has completed PIP-L5-002, that activity is down-ranked, and the example falls just below the review threshold (UNMATCHED, still manually associable). That is expected behaviour, not a failure.

**C — Unknown.** Load the unknown example (`ZZ-999 …`) → UNMATCHED with the reason "report explicitly names an unknown work package". In Review there is no one-click approve; associating it needs an explicit selection.

**D — Time Agent.**
1. Type `XX103 started at 9.` → the agent asks for the missing location ("Where is this work? My best guess is PIP-L5-009 … at R03").
2. Type `Rack 3.` → the same event is re-matched → "Matched to PIP-L5-009 … Confirm? (yes / no)".
3. Click **Yes, record it** → actual start recorded, audit row written.

Use XX103 here, because XX102 is completed in scenario A. On a fresh database, `XX102 started at 9.` instead asks "Which location is this at: R03, Unit 2?".

**E — Schedule intelligence.**
- Report `Foundation concrete poured at Area A, 40%.` and confirm CIV-L5-008 in Review with a delay cause. It is on the critical path, so the impact panel shows the forecast finish moving.
- Schedule: the Gantt shows planned and actual bars, critical and at-risk activities, and predecessors.
- Analytics: planned-vs-actual variance, productivity and delay causes.
- Audit + memory: the audit trail, and a memory search (e.g. discipline `civil`).

## Safety checks worth showing

- `Piping crew: spool XX103 at rack 3 not completed yet.` → REVIEW_REQUIRED with the reason "confident match … but the report states no progress or start to apply — its wording is negated or future tense". The extracted progress shows "—". Confirming any activity returns 422 and writes nothing.
- The same holds for "will be completed tomorrow", "not started due to rain", "has not started", "is not finished", "yet to complete", "completion is pending" and "will start tomorrow".
- After scenario A, report `Spool XX102 at rack 3 working, 30%.` and try to confirm PIP-L5-002 → 409 "PIP-L5-002 is already complete; lower progress requires explicit planner override". Nothing is written; reject the report.
- `Install pump P-301, 50%.`-style reports now carry the tag as identifier evidence, visible in the "ID" column of the candidate table.
