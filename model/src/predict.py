from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import joblib

if __package__:
    from .build_dataset import extract_pdf_text
    from .classifier import DocumentClassifier
    from .extractor import extract_document_fields
else:
    from build_dataset import extract_pdf_text
    from classifier import DocumentClassifier
    from extractor import extract_document_fields


MODEL_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = MODEL_DIR.parent
DEFAULT_MODEL_PATH = MODEL_DIR / "models" / "document_classifier.joblib"
DEFAULT_INPUT_DIR = REPOSITORY_DIR / "input"
DEFAULT_OUTPUT_DIR = REPOSITORY_DIR / "output"


def remove_empty_dirs(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def clear_previous_outputs(output_dir: Path) -> int:
    """Remove JSON results of earlier runs, so after a run output/ mirrors exactly what is
    in input/ now. Only .json files (and folders left empty) are removed."""
    if not output_dir.is_dir():
        return 0
    removed = 0
    for path in output_dir.rglob("*.json"):
        path.unlink()
        removed += 1
    remove_empty_dirs(output_dir)
    return removed


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
        try:
            text = extract_pdf_text(pdf_path)
            result = classifier.classify(text)
            document = (
                extract_document_fields(result.document_type, text)
                if result.status == "classified" and result.document_type
                else {}
            )
        except Exception as error:  # one unreadable PDF must not stop the whole batch
            results.append(
                {
                    "file": str(pdf_path),
                    "document_type": None,
                    "confidence": 0.0,
                    "nearest_example_similarity": 0.0,
                    "status": "error",
                    "error": str(error),
                    "json": {},
                }
            )
            continue
        results.append(
            {
                "file": str(pdf_path),
                "document_type": result.document_type,
                "confidence": round(result.confidence, 4),
                "nearest_example_similarity": round(
                    result.nearest_example_similarity, 4
                ),
                "status": result.status,
                "json": document,
            }
        )
    return results


def write_json_outputs(
    results: list[dict[str, object]],
    inputs: list[Path],
    output_dir: Path,
) -> list[Path]:
    input_roots = sorted(
        (path.resolve() for path in inputs if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    destinations = []
    for result in results:
        source = Path(str(result["file"])).resolve()
        input_root = next(
            (root for root in input_roots if source.is_relative_to(root)),
            None,
        )
        relative_path = source.relative_to(input_root) if input_root else Path(source.name)
        destinations.append((output_dir / relative_path).with_suffix(".json"))

    if len(set(destinations)) != len(destinations):
        raise ValueError(
            "Multiple input PDFs map to the same output filename. "
            "Pass a common input folder to preserve their directory structure."
        )

    for result, destination in zip(results, destinations):
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Documents outside the supported types get an empty .json file (UZP requirement).
        content = (
            json.dumps(result["json"], ensure_ascii=False, indent=2) + "\n"
            if result["json"]
            else ""
        )
        destination.write_text(content, encoding="utf-8")
    return destinations


def main() -> None:
    started_at = time.perf_counter()
    parser = argparse.ArgumentParser(
        description=(
            "Classify PDFs by their text and extract the matching JSON fields."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        default=[DEFAULT_INPUT_DIR],
        help="PDF files or folders (default: input/).",
    )
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--keep-output",
        action="store_true",
        help="Do not remove results of earlier runs from the default output/ folder.",
    )
    args = parser.parse_args()
    try:
        # Start every run with a clean output/, so it holds only results for the current
        # input/. A custom --output-dir is never cleared.
        if not args.keep_output and args.output_dir.resolve() == DEFAULT_OUTPUT_DIR.resolve():
            clear_previous_outputs(args.output_dir)
        classifier = load_classifier(args.model_path)
        results = predict(pdf_paths(args.inputs), classifier)
        outputs = write_json_outputs(results, args.inputs, args.output_dir)
    except (FileNotFoundError, OSError, ValueError) as error:
        parser.error(str(error))
    elapsed_seconds = time.perf_counter() - started_at
    for result, output_path in zip(results, outputs):
        print(
            json.dumps(
                {
                    "file": result["file"],
                    "output": str(output_path),
                    "document_type": result["document_type"],
                    "confidence": result["confidence"],
                    "status": result["status"],
                    **({"error": result["error"]} if "error" in result else {}),
                },
                ensure_ascii=False,
            )
        )
    print(f"Processing completed in {elapsed_seconds:.2f} seconds.", file=sys.stderr)


if __name__ == "__main__":
    main()