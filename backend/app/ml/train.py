"""
Train the risk-prediction classifier.

RandomForest over the FEATURE_COLUMNS schema. Chosen because:
  - Tabular features, ~2k rows: trees beat anything deep on this scale.
  - sklearn is already in requirements.txt (no XGBoost dependency).
  - feature_importances_ gives an immediate explainability story for the
    research write-up.

Outputs (under app/ml/data/):
  - model.pkl        : joblib-pickled RandomForestClassifier
  - metrics.json     : accuracy, macro-F1, per-class report, confusion matrix
  - feature_importance.json

Run:  python -m app.ml.train --csv app/ml/data/training.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import train_test_split

from app.ml.features import FEATURE_COLUMNS, RISK_CLASSES


def _load_csv(path: Path) -> tuple[list[list[float]], list[str]]:
    """
    Plain stdlib CSV loader so we don't pull pandas just for one read.
    Returns (X, y) — X is a list of feature rows in FEATURE_COLUMNS order.
    """
    import csv

    X: list[list[float]] = []
    y: list[str] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            X.append([float(row[c]) for c in FEATURE_COLUMNS])
            y.append(row["risk_label"])
    return X, y


def train(
    csv_path: Path,
    out_dir: Path,
    test_size: float = 0.2,
    seed: int = 42,
) -> dict:
    X, y = _load_csv(csv_path)
    if not X:
        raise ValueError(f"Training CSV is empty: {csv_path}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed, stratify=y
    )

    # n_estimators=200 / max_depth=None is a safe default for ~2k rows.
    # class_weight='balanced' protects us if the synthetic distribution
    # drifts away from uniform (or once real data takes over).
    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=None,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=seed,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    metrics = {
        "n_train": len(X_train),
        "n_test": len(X_test),
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "macro_f1": float(f1_score(y_test, y_pred, average="macro")),
        "report": classification_report(
            y_test, y_pred, labels=list(RISK_CLASSES), output_dict=True, zero_division=0,
        ),
        "confusion_matrix": {
            "labels": list(RISK_CLASSES),
            "matrix": confusion_matrix(y_test, y_pred, labels=list(RISK_CLASSES)).tolist(),
        },
    }

    importance = sorted(
        (
            {"feature": name, "importance": float(imp)}
            for name, imp in zip(FEATURE_COLUMNS, model.feature_importances_)
        ),
        key=lambda d: d["importance"],
        reverse=True,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "feature_columns": list(FEATURE_COLUMNS),
            "classes": list(model.classes_),
        },
        out_dir / "model.pkl",
    )
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (out_dir / "feature_importance.json").write_text(json.dumps(importance, indent=2))

    return metrics


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Train the risk-prediction model.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path(__file__).parent / "data" / "training.csv",
        help="Training CSV (produced by app.ml.dataset).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).parent / "data",
        help="Where to write model.pkl + metrics.json.",
    )
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    metrics = train(args.csv, args.out_dir, args.test_size, args.seed)
    print(f"Trained on {metrics['n_train']} rows, evaluated on {metrics['n_test']}.")
    print(f"Accuracy: {metrics['accuracy']:.3f}   Macro-F1: {metrics['macro_f1']:.3f}")
    print(f"Saved model + metrics to {args.out_dir}")


if __name__ == "__main__":
    main()
