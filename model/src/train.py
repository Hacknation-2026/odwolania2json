from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
from sklearn.metrics import accuracy_score, classification_report

if __package__:
    from .classifier import (
        DEFAULT_MIN_CONFIDENCE,
        UNSUPPORTED_LABEL,
        DocumentClassifier,
    )
else:
    from classifier import DEFAULT_MIN_CONFIDENCE, UNSUPPORTED_LABEL, DocumentClassifier


MODEL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = MODEL_DIR / "data" / "processed"
DEFAULT_MODEL_PATH = MODEL_DIR / "models" / "document_classifier.joblib"


def read_split(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Dataset split not found: {path}")

    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON in {path}, line {line_number}: {error}") from error
        if not isinstance(row, dict):
            raise ValueError(f"Expected a JSON object in {path}, line {line_number}.")
        text = row.get("input_text")
        label = row.get("document_type")
        if not isinstance(text, str) or not isinstance(label, str):
            raise ValueError(
                f"Expected string input_text and document_type in {path}, "
                f"line {line_number}."
            )
        rows.append(row)
    if not rows:
        raise ValueError(f"No training examples found in: {path}")
    return rows


def train(
    data_dir: Path,
    model_path: Path,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> None:
    train_rows = read_split(data_dir / "train.jsonl")
    test_rows = read_split(data_dir / "test.jsonl")

    classifier = DocumentClassifier.fit(
        [row["input_text"] for row in train_rows],
        [row["document_type"] for row in train_rows],
        min_confidence=min_confidence,
    )
    expected = [row["document_type"] for row in test_rows]
    predictions = []
    for row in test_rows:
        result = classifier.classify(row["input_text"])
        if result.status == "unsupported":
            predictions.append(UNSUPPORTED_LABEL)
        else:
            predictions.append(result.document_type or "__uncertain__")
    print(f"Test accuracy: {accuracy_score(expected, predictions):.3f}")
    print(
        classification_report(
            expected,
            predictions,
            labels=sorted(set(expected) | set(predictions)),
            zero_division=0,
        )
    )

    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(classifier.to_artifact(), model_path)
    print(f"Trained model written to: {model_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train a content-based classifier for KIO case documents."
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=DEFAULT_MIN_CONFIDENCE,
        help="Reject predictions below this probability (0 to 1).",
    )
    args = parser.parse_args()
    try:
        train(args.data_dir, args.model_path, args.min_confidence)
    except (FileNotFoundError, OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()