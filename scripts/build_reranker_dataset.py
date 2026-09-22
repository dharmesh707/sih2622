import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import extract_event, score_candidate


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmark" / "generated"

TRAIN_FILE = CORPUS / "train.jsonl"
SCHEDULE_FILE = CORPUS / "schedule.csv"

OUTPUT_CSV = CORPUS / "reranker_train.csv"
OUTPUT_JSONL = CORPUS / "reranker_train.jsonl"

TOP_K = 20


def main() -> None:
    if not TRAIN_FILE.exists():
        raise SystemExit(
            "Run: python scripts/generate_corpus.py first"
        )

    if not SCHEDULE_FILE.exists():
        raise SystemExit(
            "Missing benchmark/generated/schedule.csv"
        )

    with SCHEDULE_FILE.open(
        encoding="utf-8",
        newline="",
    ) as handle:
        activities = list(csv.DictReader(handle))

    reports = [
        json.loads(line)
        for line in TRAIN_FILE.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    # Keep this identical to the current benchmark.
    # Terminology-map integration can be added later as a
    # separate controlled experiment.
    terms = []

    rows = []

    for report_index, report in enumerate(reports, start=1):
        event = extract_event(
            report["text"],
            "reranker_training",
            report_index,
        )

        ranked = []

        for activity in activities:
            scores, _ = score_candidate(
                event,
                activity,
                terms,
            )

            identifier_match = int(
                any(
                    str(identifier).lower() in str(
                        activity["activity_code"]
                    ).lower()
                    or str(identifier).lower() in str(
                        activity["description"]
                    ).lower()
                    for identifier in event["identifiers"]
                )
            )

            discipline_match = int(
                bool(event.get("discipline"))
                and event["discipline"]
                == activity["discipline"]
            )

            location_match = int(
                bool(event.get("location_terms"))
                and str(event["location_terms"]).lower()
                == str(activity["location"]).lower()
            )

            ranked.append(
                {
                    "activity": activity,
                    "scores": scores,
                    "identifier_match": identifier_match,
                    "discipline_match": discipline_match,
                    "location_match": location_match,
                }
            )

        ranked.sort(
            key=lambda item: item["scores"]["fused_score"],
            reverse=True,
        )

        top_score = ranked[0]["scores"]["fused_score"]
        second_score = (
            ranked[1]["scores"]["fused_score"]
            if len(ranked) > 1
            else 0.0
        )

        margin = top_score - second_score

        selected = ranked[:TOP_K]

        # Always include the true activity when it exists,
        # even if the baseline ranked it outside top-K.
        truth = report["truth"]

        if truth:
            truth_item = next(
                (
                    item
                    for item in ranked
                    if item["activity"]["activity_code"] == truth
                ),
                None,
            )

            if truth_item and truth_item not in selected:
                selected.append(truth_item)

        rank_lookup = {
            id(item): rank
            for rank, item in enumerate(ranked, start=1)
        }

        for item in selected:
            activity = item["activity"]
            scores = item["scores"]

            baseline_rank = rank_lookup[id(item)]

            label = int(
                truth is not None
                and activity["activity_code"] == truth
            )

            rows.append(
                {
                    "report_index": report_index,
                    "report_text": report["text"],
                    "truth_activity": truth or "",
                    "candidate_activity": activity["activity_code"],
                    "candidate_description": activity["description"],
                    "candidate_discipline": activity["discipline"],
                    "candidate_location": activity["location"],
                    "label": label,

                    # Existing matcher features
                    "score_id": scores["score_id"],
                    "score_lexical": scores["score_lexical"],
                    "score_semantic": scores["score_semantic"],
                    "score_context": scores["score_context"],
                    "temporal_factor": scores["temporal_factor"],
                    "fused_score": scores["fused_score"],

                    # Ranking features
                    "baseline_rank": baseline_rank,
                    "gap_from_top": top_score
                    - scores["fused_score"],
                    "top_score": top_score,
                    "second_score": second_score,
                    "margin": margin,

                    # Explicit context features
                    "identifier_match": item["identifier_match"],
                    "discipline_match": item["discipline_match"],
                    "location_match": item["location_match"],
                }
            )

    fieldnames = list(rows[0].keys())

    with OUTPUT_CSV.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)

    with OUTPUT_JSONL.open(
        "w",
        encoding="utf-8",
    ) as handle:
        for row in rows:
            handle.write(
                json.dumps(row)
                + "\n"
            )

    positives = sum(
        row["label"] == 1
        for row in rows
    )

    negatives = sum(
        row["label"] == 0
        for row in rows
    )

    reports_with_truth = sum(
        report["truth"] is not None
        for report in reports
    )

    print(f"Training reports: {len(reports)}")
    print(f"Reports with known truth: {reports_with_truth}")
    print(f"Candidate rows: {len(rows)}")
    print(f"Positive candidates: {positives}")
    print(f"Negative candidates: {negatives}")
    print(f"Saved: {OUTPUT_CSV}")
    print(f"Saved: {OUTPUT_JSONL}")


if __name__ == "__main__":
    main()