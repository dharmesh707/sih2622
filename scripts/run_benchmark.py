"""Score the v2 benchmark through the production path (POST /api/v1/reports -> make_match -> routing).

Usage:  python scripts/run_benchmark.py [--split held_out|dev] [--reranker]

Uses a throwaway SQLite DB, imports both benchmark schedules through the real import endpoint, and submits
every case to project 2 with report_date = the manifest's data date (reproducible temporal scores).
Refuses to run if a benchmark file no longer matches MANIFEST.json (held-out is frozen).
Synthetic, small corpus: numbers describe this benchmark only, not production accuracy.
"""
import argparse
import hashlib
import json
import os
import statistics
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parents[1]
BENCH = ROOT / "benchmark" / "v2"
parser = argparse.ArgumentParser()
parser.add_argument("--split", choices=["held_out", "dev"], default="held_out")
parser.add_argument("--reranker", action="store_true", help="score with PROGRESSSYNC_USE_RERANKER=true")
args = parser.parse_args()

manifest = json.loads((BENCH / "MANIFEST.json").read_text(encoding="utf-8"))
for name, digest in manifest["sha256"].items():
    if hashlib.sha256((BENCH / name).read_bytes()).hexdigest() != digest:
        raise SystemExit(f"{name} does not match MANIFEST.json; the benchmark is frozen. Refusing to score.")

os.environ["PROGRESSSYNC_DB"] = str(Path(tempfile.mkdtemp()) / "bench.db")
os.environ["PROGRESSSYNC_USE_RERANKER"] = "true" if args.reranker else "false"
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402

cases = [json.loads(line) for line in (BENCH / f"{args.split}.jsonl").read_text(encoding="utf-8").splitlines() if line]
results = []
with TestClient(app) as client:
    for pid, name in ((manifest["project_id"], "schedule_project2.csv"), (manifest["distractor_project_id"], "schedule_project3.csv")):
        imported = client.post(f"/api/v1/projects/{pid}/schedule/import", files={"file": (name, (BENCH / name).read_bytes(), "text/csv")}).json()
        assert not imported["errors"], imported["errors"]
    codes = {pid: {a["id"]: a["activity_code"] for a in client.get(f"/api/v1/projects/{pid}/activities").json()} for pid in (2, 3)}
    for c in cases:
        body = client.post("/api/v1/reports", json={"project_id": 2, "text": c["text"], "report_date": manifest["data_date"]}).json()
        ranked = client.get(f"/api/v1/events/{body['event_id']}/candidates").json()
        ranked_codes = [codes[2].get(r["activity_id"]) for r in ranked]
        decision, top = body["match"]["decision"], ranked_codes[0] if ranked_codes else None
        results.append({**c, "decision": decision, "top": top, "correct_top1": top == c["truth"],
                        "in_top5": c["truth"] in ranked_codes[:5], "cross_project": sum(r["activity_id"] in codes[3] for r in ranked),
                        "silent_error": decision == "AUTO_MATCHED" and top != c["truth"], "latency_ms": body["latency_ms"],
                        "top_score": body["match"]["top_score"], "margin": body["match"]["margin"]})


def pct(n, d):
    return f"{100 * n / d:5.1f}%" if d else "  n/a"


truth = [r for r in results if r["truth"]]
auto = [r for r in results if r["decision"] == "AUTO_MATCHED"]
unknown = [r for r in results if r["truth"] is None]
print(f"ProgressSync benchmark v2 · split={args.split} · cases={len(results)} · reranker={'on' if args.reranker else 'off'} · data date {manifest['data_date']}")
print("Synthetic corpus; not production accuracy.\n")
print(f"Auto-match precision        {pct(sum(not r['silent_error'] for r in auto), len(auto))}  ({len(auto)} auto-matched)")
print(f"Silent errors (wrong AUTO)  {sum(r['silent_error'] for r in results)}")
print(f"Routing AUTO/REVIEW/UNMATCH {pct(len(auto), len(results))} / {pct(sum(r['decision'] == 'REVIEW_REQUIRED' for r in results), len(results))} / {pct(sum(r['decision'] == 'UNMATCHED' for r in results), len(results))}")
print(f"Top-1 accuracy (truth cases) {pct(sum(r['correct_top1'] for r in truth), len(truth))}  (n={len(truth)})")
print(f"Recall@5 (truth cases)      {pct(sum(r['in_top5'] for r in truth), len(truth))}")
print(f"No-truth cases UNMATCHED    {pct(sum(r['decision'] == 'UNMATCHED' for r in unknown), len(unknown))}  (n={len(unknown)}; AUTO on these = silent error)")
print(f"Cross-project candidates    {sum(r['cross_project'] for r in results)}")
print(f"Median server latency       {statistics.median(r['latency_ms'] for r in results):.1f} ms\n")
print(f"{'category':18} {'n':>3} {'top1':>7} {'R@5':>7} {'AUTO':>5} {'REVIEW':>6} {'UNM':>4} {'silent':>6}")
by_cat = defaultdict(list)
for r in results:
    by_cat[r["category"]].append(r)
for cat, rows in sorted(by_cat.items()):
    t = [r for r in rows if r["truth"]]
    print(f"{cat:18} {len(rows):3} {pct(sum(r['correct_top1'] for r in t), len(t)):>7} {pct(sum(r['in_top5'] for r in t), len(t)):>7} "
          f"{sum(r['decision'] == 'AUTO_MATCHED' for r in rows):5} {sum(r['decision'] == 'REVIEW_REQUIRED' for r in rows):6} {sum(r['decision'] == 'UNMATCHED' for r in rows):4} {sum(r['silent_error'] for r in rows):6}")

out = BENCH / "results" / f"{args.split}{'_reranker' if args.reranker else ''}.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({"split": args.split, "reranker": args.reranker, "cases": results}, indent=1) + "\n", encoding="utf-8")
print(f"\nPer-case results: {out.relative_to(ROOT)}")
