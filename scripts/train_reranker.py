import csv
import json
import pickle
from pathlib import Path

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "benchmark" / "generated" / "reranker_train.csv"
ARTIFACTS = ROOT / "ml_artifacts"

MODEL_PATH = ARTIFACTS / "reranker_v0.1.pkl"
METRICS_PATH = ARTIFACTS / "reranker_v0.1_metrics.json"


FEATURES = [
    "score_id",
    "score_lexical",
    "score_semantic",
    "score_context",
    "temporal_factor",
    "fused_score",
    "baseline_rank",
    "gap_from_top",
    "margin",
    "identifier_match",
    "discipline_match",
    "location_match",
]


def read_rows():
    with DATA.open(
        encoding="utf-8",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def main():
    rows = read_rows()



    groups = [
        int(row["report_index"])
        for row in rows
    ]

    X = [
        [float(row[feature]) for feature in FEATURES]
        for row in rows
    ]

    y = [
        int(row["label"])
        for row in rows
    ]

    splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=0.2,
        random_state=42,
    )

    train_idx, val_idx = next(
        splitter.split(X, y, groups)
    )

    X_train = [X[i] for i in train_idx]
    X_val = [X[i] for i in val_idx]

    y_train = [y[i] for i in train_idx]
    y_val = [y[i] for i in val_idx]

    model = LogisticRegression(
        class_weight="balanced",
        max_iter=2000,
        random_state=42,
    )

    model.fit(
        X_train,
        y_train,
    )

    probabilities = model.predict_proba(X_val)[:, 1]

    predictions = [
        1 if p >= 0.5 else 0
        for p in probabilities
    ]

    print("Training rows:", len(train_idx))
    print("Validation rows:", len(val_idx))
    print("Training reports:",
          len(set(groups[i] for i in train_idx)))
    print("Validation reports:",
          len(set(groups[i] for i in val_idx)))

    print("\nClassification report:")
    print(
        classification_report(
            y_val,
            predictions,
            digits=4,
            zero_division=0,
        )
    )

    if len(set(y_val)) > 1:
        auc = roc_auc_score(
            y_val,
            probabilities,
        )
        print(f"Validation ROC-AUC: {auc:.4f}")
    else:
        auc = None
        print("Validation ROC-AUC: unavailable")

    ARTIFACTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    artifact = {
        "model": model,
        "features": FEATURES,
        "version": "0.1.0",
        "model_type": "logistic_regression",
        "training_rows": len(train_idx),
        "validation_rows": len(val_idx),
        "training_reports": len(
            set(groups[i] for i in train_idx)
        ),
        "validation_reports": len(
            set(groups[i] for i in val_idx)
        ),
    }

    with MODEL_PATH.open("wb") as f:
        pickle.dump(
            artifact,
            f,
        )

    metrics = {
        "version": "0.1.0",
        "model_type": "logistic_regression",
        "validation_roc_auc": auc,
        "training_rows": len(train_idx),
        "validation_rows": len(val_idx),
    }

    METRICS_PATH.write_text(
        json.dumps(
            metrics,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nSaved model:")
    print(MODEL_PATH)

    print("\nSaved metrics:")
    print(METRICS_PATH)


if __name__ == "__main__":
    main()