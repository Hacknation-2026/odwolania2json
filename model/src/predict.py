from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib

if __package__:
    from .build_dataset import extract_pdf_text
    from .classifier import DocumentClassifier
else:
    from build_dataset import extract_pdf_text
    from classifier import DocumentClassifier


MODEL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = MODEL_DIR / "models" / "document_classifier.joblib"


def load_classifier(model_path: Path) -> DocumentClassifier:
    if not model_path.is_file():
        raise FileNotFoundError(
            f"Trained model not found: {model_path}. Run train.py first."
        )
    artifact = joblib.load(model_path)
    if not isinstance(artifact, dict):
        raise ValueError(f"Invalid classifier artifact: {model_path}")
    return DocumentClassifier.from_artifact(artifact)


def pdf_paths(inputs: list[Path]) -> list[Path]:
    paths = []
    for input_path in inputs:
        if not input_path.exists():
            raise FileNotFoundError(f"Input path does not exist: {input_path}")
        if input_path.is_file():
            if input_path.suffix.lower() != ".pdf":
                raise ValueError(f"Expected a PDF file: {input_path}")
            paths.append(input_path)
        elif input_path.is_dir():
            paths.extend(
                path
                for path in sorted(input_path.rglob("*"))
                if path.is_file() and path.suffix.lower() == ".pdf"
            )
    if not paths:
        raise ValueError("No PDF files found in the supplied paths.")
    return paths


def predict(paths: list[Path], classifier: DocumentClassifier) -> list[dict[str, object]]:
    results = []
    for pdf_path in paths:
        result = classifier.classify(extract_pdf_text(pdf_path))
        results.append(
            {
                "file": str(pdf_path),
                "document_type": result.document_type,
                "confidence": round(result.confidence, 4),
                "nearest_example_similarity": round(
                    result.nearest_example_similarity, 4
                ),
                "status": result.status,
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify PDFs by their text, without using their filenames."
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="PDF files or folders.")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    args = parser.parse_args()
    try:
        classifier = load_classifier(args.model_path)
        results = predict(pdf_paths(args.inputs), classifier)
    except (FileNotFoundError, OSError, ValueError) as error:
        parser.error(str(error))
    for result in results:
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()