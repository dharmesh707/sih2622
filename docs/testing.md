# Testing

Prerequisite: `python scripts/provision_model.py` once per machine. Without the model, `pytest` exits immediately with that instruction.

## Backend tests

`pytest -q` runs every test against a temporary SQLite database:

| File | Covers |
|---|---|
| `tests/test_pipeline.py` | Original end-to-end API tests (report, review, confirm, agent, import) |
| `tests/test_safety.py` | `norm()` regressions, discipline and completion inference, confirm/reject state machine, 404/409/422 handling, reassign audit, multi-project isolation, B-14 ID regression |
| `tests/test_schedule.py` | Dependency import (inline and dependency-only), cycle rejection, FS/SS/FF maths, actual-driven forecast, at-risk rule, seed consistency |
| `tests/test_analytics.py` | Actual duration (null until finished), variance, delay causes, execution memory, project-aware filters |
| `tests/test_time_agent.py` | Session persistence, clarification on the same event, yes/no, max rounds, pick by code |
| `tests/test_terminology.py` | YAML is the source of truth; every mapping is applied; invalid files are rejected |
| `tests/test_matching.py` | Exact, synonym, abbreviation, typo/OCR, near duplicate, unknown, wrong discipline |
| `tests/test_negation.py` | F-01: negated and future-tense wording infers no progress, start or finish, is never AUTO and never written (422); positive controls still work |
| `tests/test_progress_policy.py` | F-02/F-13: no reopening or lowering of progress (409), idempotent repeat completion, forward progress, completed-twin down-ranking, concurrent confirms approve once |
| `tests/test_awaiting.py` | F-03: pending AUTO_MATCHED events listed until confirmed, rejected or sent to review; abandoned Time Agent confirmations reachable; project-scoped |
| `tests/test_identifiers.py` | F-04: single-letter tags and line numbers extracted, random numbers ignored, evidence reaches the right candidate, no cross-project leakage |
| `tests/test_freshness.py` | F-05: forecast and at-risk refresh when the data date moves |
| `tests/test_hardening.py` | F-08 future report dates, F-10 agent sessions never cross projects, F-11 whole-token code selection |

## Benchmark

`python scripts/run_benchmark.py [--split held_out|dev] [--reranker]` scores `benchmark/v2`:
- 82 activities in project 2, plus a look-alike distractor project 3.
- 140 synthetic field reports in 10 categories, split into 56 dev and 84 held-out cases.
- Every case goes through `POST /api/v1/reports` with a fixed report date.
- The held-out split is frozen by SHA-256 in `benchmark/v2/MANIFEST.json`; the runner refuses changed files.
- `scripts/build_benchmark.py` regenerates the files deterministically.

The numbers describe this small synthetic benchmark only. See PROGRESS.md for the recorded runs.

## Browser E2E

This is manual, using the Chrome DevTools MCP against `uvicorn` on port 8000 with the built React app and a freshly reset database. The steps are in `docs/demo.md` (scenarios A–E and the safety checks). Mobile layout is checked with 390×844 emulation. There is no automated browser suite in the repository.

Benchmark per-case output goes to `benchmark/v2/results/`. It is regenerated on every run and is not committed.
