import csv, json, statistics, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from backend.app import extract_event, score_candidate

ROOT=Path(__file__).parents[1]; corpus=ROOT/'benchmark'/'generated'
if not (corpus/'held_out.jsonl').exists():
    raise SystemExit('Run python scripts/generate_corpus.py first')
with (corpus/'schedule.csv').open(encoding='utf-8') as handle: activities=list(csv.DictReader(handle))
reports=[json.loads(line) for line in (corpus/'held_out.jsonl').read_text(encoding='utf-8').splitlines() if line]
terms=[]; results=[]; latencies=[]
for report in reports:
    started=time.perf_counter(); event=extract_event(report['text'],'benchmark',1); ranked=[]
    for activity in activities:
        scores,evidence=score_candidate(event, activity, terms); ranked.append((scores['fused_score'], activity['activity_code'], scores))
    ranked.sort(reverse=True); top=ranked[0]; second=ranked[1]; margin=top[0]-second[0]
    decision='AUTO_MATCHED' if top[0]>=.82 and margin>=.12 else 'REVIEW_REQUIRED' if top[0]>=.45 else 'UNMATCHED'
    correct=report['truth'] == top[1]
    results.append((decision, correct, report['truth'] is None, any(item[1]==report['truth'] for item in ranked[:5])))
    latencies.append((time.perf_counter()-started)*1000)
auto=[r for r in results if r[0]=='AUTO_MATCHED']; print(f'Held-out cases: {len(results)}'); print(f'Auto-match precision: {sum(r[1] for r in auto)/len(auto)*100 if auto else 0:.1f}%'); print(f'Silent errors: {sum(not r[1] and r[0]=="AUTO_MATCHED" for r in results)}'); print(f'Auto-match rate: {sum(r[0]=="AUTO_MATCHED" for r in results)/len(results)*100:.1f}%'); print(f'Review rate: {sum(r[0]=="REVIEW_REQUIRED" for r in results)/len(results)*100:.1f}%'); print(f'Unmatched rate: {sum(r[0]=="UNMATCHED" for r in results)/len(results)*100:.1f}%'); print(f'Recall@5: {sum(r[3] for r in results)/len(results)*100:.1f}%'); print(f'Median latency: {statistics.median(latencies):.2f} ms')
