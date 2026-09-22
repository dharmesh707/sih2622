import csv
import json
import pickle
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import extract_event, score_candidate


ROOT = Path(__file__).resolve().parents[1]

CORPUS = ROOT / "benchmark" / "generated"
MODEL_PATH = ROOT / "ml_artifacts" / "reranker_v0.1.pkl"


def decision_from_fused(top, second):
    margin = top - second

    if top >= 0.82 and margin >= 0.12:
        return "AUTO_MATCHED"

    if top >= 0.45:
        return "REVIEW_REQUIRED"

    return "UNMATCHED"


def decision_from_reranker(top_probability, second_probability):
    margin = top_probability - second_probability

    if top_probability >= 0.90 and margin >= 0.10:
        return "AUTO_MATCHED"

    if top_probability >= 0.50:
        return "REVIEW_REQUIRED"

    return "UNMATCHED"


def main():
    with MODEL_PATH.open("rb") as f:
        artifact = pickle.load(f)

    model = artifact["model"]
    features = artifact["features"]

    with (CORPUS / "schedule.csv").open(
        encoding="utf-8"
    ) as f:
        activities = list(csv.DictReader(f))

    reports = [
        json.loads(line)
        for line in (
            CORPUS / "held_out.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    baseline_results = []
    reranker_results = []

    baseline_latencies = []
    reranker_latencies = []

    for index, report in enumerate(reports, 1):

        # =====================================================
        # BASELINE
        # =====================================================

        start_time = time.perf_counter()

        event = extract_event(
            report["text"],
            "benchmark",
            1,
        )

        ranked = []

        for activity in activities:
            scores, _ = score_candidate(
                event,
                activity,
                [],
            )

            ranked.append(
                {
                    "activity": activity,
                    "scores": scores,
                }
            )

        ranked.sort(
            key=lambda x: x["scores"]["fused_score"],
            reverse=True,
        )

        baseline_latencies.append(
            (time.perf_counter() - start_time) * 1000
        )

        baseline_top = ranked[0]
        baseline_second = ranked[1]

        baseline_score = baseline_top["scores"]["fused_score"]
        baseline_second_score = (
            baseline_second["scores"]["fused_score"]
        )

        baseline_decision = decision_from_fused(
            baseline_score,
            baseline_second_score,
        )

        baseline_top_code = baseline_top[
            "activity"
        ]["activity_code"]

        baseline_correct = (
            baseline_top_code == report["truth"]
        )

        baseline_recall5 = any(
            item["activity"]["activity_code"]
            == report["truth"]
            for item in ranked[:5]
        )

        # =====================================================
        # RERANKER
        # =====================================================

        reranker_start = time.perf_counter()

        top_score = ranked[0]["scores"]["fused_score"]
        second_score = ranked[1]["scores"]["fused_score"]
        baseline_margin = top_score - second_score

        reranked = []

        for rank, item in enumerate(ranked[:20], start=1):

            activity = item["activity"]
            scores = item["scores"]

            identifier_match = int(
                any(
                    str(identifier).lower()
                    in str(activity["activity_code"]).lower()
                    or str(identifier).lower()
                    in str(activity["description"]).lower()
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

            feature_values = {
                "score_id": scores["score_id"],
                "score_lexical": scores["score_lexical"],
                "score_semantic": scores["score_semantic"],
                "score_context": scores["score_context"],
                "temporal_factor": scores["temporal_factor"],
                "fused_score": scores["fused_score"],
                "baseline_rank": rank,
                "gap_from_top": (
                    top_score
                    - scores["fused_score"]
                ),
                "margin": baseline_margin,
                "identifier_match": identifier_match,
                "discipline_match": discipline_match,
                "location_match": location_match,
            }

            vector = [
                feature_values[name]
                for name in features
            ]

            probability = model.predict_proba(
                [vector]
            )[0][1]

            reranked.append(
                {
                    "activity": activity,
                    "probability": probability,
                    "baseline_rank": rank,
                }
            )

        reranked.sort(
            key=lambda x: x["probability"],
            reverse=True,
        )

        reranker_latencies.append(
            (time.perf_counter() - reranker_start) * 1000
        )

        reranker_top = reranked[0]
        reranker_second = reranked[1]

        reranker_probability = (
            reranker_top["probability"]
        )

        reranker_second_probability = (
            reranker_second["probability"]
        )

        reranker_decision = decision_from_reranker(
            reranker_probability,
            reranker_second_probability,
        )

        reranker_top_code = reranker_top[
            "activity"
        ]["activity_code"]

        reranker_correct = (
            reranker_top_code == report["truth"]
        )

        reranker_recall5 = any(
            item["activity"]["activity_code"]
            == report["truth"]
            for item in reranked[:5]
        )

        baseline_results.append(
            {
                "decision": baseline_decision,
                "correct": baseline_correct,
                "recall5": baseline_recall5,
            }
        )

        reranker_results.append(
            {
                "decision": reranker_decision,
                "correct": reranker_correct,
                "recall5": reranker_recall5,
            }
        )

        print(f"\nCASE {index}")
        print("Report:", report["text"])
        print("Truth:", report["truth"])

        print(
            "Baseline:",
            baseline_top_code,
            f"score={baseline_score:.4f}",
            f"decision={baseline_decision}",
        )

        print(
            "Reranker:",
            reranker_top_code,
            f"prob={reranker_probability:.4f}",
            f"decision={reranker_decision}",
        )

        print(
            "Baseline correct:",
            baseline_correct,
            "| Reranker correct:",
            reranker_correct,
        )

    # =========================================================
    # METRICS
    # =========================================================

    def calculate_metrics(results):
        auto = [
            r
            for r in results
            if r["decision"] == "AUTO_MATCHED"
        ]

        auto_precision = (
            sum(r["correct"] for r in auto)
            / len(auto)
            * 100
            if auto
            else 0.0
        )

        silent_errors = sum(
            not r["correct"]
            and r["decision"] == "AUTO_MATCHED"
            for r in results
        )

        auto_rate = (
            sum(
                r["decision"] == "AUTO_MATCHED"
                for r in results
            )
            / len(results)
            * 100
        )

        review_rate = (
            sum(
                r["decision"] == "REVIEW_REQUIRED"
                for r in results
            )
            / len(results)
            * 100
        )

        unmatched_rate = (
            sum(
                r["decision"] == "UNMATCHED"
                for r in results
            )
            / len(results)
            * 100
        )

        recall5 = (
            sum(r["recall5"] for r in results)
            / len(results)
            * 100
        )

        top1 = (
            sum(r["correct"] for r in results)
            / len(results)
            * 100
        )

        return {
            "auto_precision": auto_precision,
            "silent_errors": silent_errors,
            "auto_rate": auto_rate,
            "review_rate": review_rate,
            "unmatched_rate": unmatched_rate,
            "recall5": recall5,
            "top1": top1,
        }

    baseline = calculate_metrics(
        baseline_results
    )

    reranker = calculate_metrics(
        reranker_results
    )

    print("\n")
    print("=" * 60)
    print("BASELINE")
    print("=" * 60)

    print(
        f"Top-1 accuracy:       {baseline['top1']:.1f}%"
    )
    print(
        f"Auto-match precision: {baseline['auto_precision']:.1f}%"
    )
    print(
        f"Silent errors:        {baseline['silent_errors']}"
    )
    print(
        f"Auto-match rate:      {baseline['auto_rate']:.1f}%"
    )
    print(
        f"Review rate:          {baseline['review_rate']:.1f}%"
    )
    print(
        f"Unmatched rate:       {baseline['unmatched_rate']:.1f}%"
    )
    print(
        f"Recall@5:             {baseline['recall5']:.1f}%"
    )
    print(
        f"Median latency:       "
        f"{statistics.median(baseline_latencies):.2f} ms"
    )

    print("\n")
    print("=" * 60)
    print("RERANKER")
    print("=" * 60)

    print(
        f"Top-1 accuracy:       {reranker['top1']:.1f}%"
    )
    print(
        f"Auto-match precision: {reranker['auto_precision']:.1f}%"
    )
    print(
        f"Silent errors:        {reranker['silent_errors']}"
    )
    print(
        f"Auto-match rate:      {reranker['auto_rate']:.1f}%"
    )
    print(
        f"Review rate:          {reranker['review_rate']:.1f}%"
    )
    print(
        f"Unmatched rate:       {reranker['unmatched_rate']:.1f}%"
    )
    print(
        f"Recall@5:             {reranker['recall5']:.1f}%"
    )
    print(
        f"Median latency:       "
        f"{statistics.median(reranker_latencies):.2f} ms"
    )

    print("\n")
    print("=" * 60)
    print("COMPARISON")
    print("=" * 60)

    print(
        "Top-1:",
        f"{baseline['top1']:.1f}% -> "
        f"{reranker['top1']:.1f}%"
    )

    print(
        "Recall@5:",
        f"{baseline['recall5']:.1f}% -> "
        f"{reranker['recall5']:.1f}%"
    )

    print(
        "Auto precision:",
        f"{baseline['auto_precision']:.1f}% -> "
        f"{reranker['auto_precision']:.1f}%"
    )

    print(
        "Silent errors:",
        f"{baseline['silent_errors']} -> "
        f"{reranker['silent_errors']}"
    )

    print(
        "Auto-match rate:",
        f"{baseline['auto_rate']:.1f}% -> "
        f"{reranker['auto_rate']:.1f}%"
    )

    print(
        "Median latency:",
        f"{statistics.median(baseline_latencies):.2f} ms -> "
        f"{statistics.median(reranker_latencies):.2f} ms"
    )


if __name__ == "__main__":
    main()