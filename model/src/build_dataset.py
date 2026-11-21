from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

import pymupdf

try:
    from .classifier import UNSUPPORTED_LABEL
except ImportError:
    from classifier import UNSUPPORTED_LABEL


MODEL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = MODEL_DIR / "data" / "raw"
DEFAULT_OUTPUT_DIR = MODEL_DIR / "data" / "processed"
LABEL_FILENAME_BY_PDF = {
    "potwierdzenie_przelewu.pdf": "przelew.json",
}


def extract_pdf_text(pdf_path: Path) -> str:
    try:
        with pymupdf.open(pdf_path) as document:
            pages = [page.get_text("text", sort=True).strip() for page in document]
    except pymupdf.FileDataError as error:
        raise ValueError(f"Could not open PDF: {pdf_path}") from error

    text = "\n\n".join(page for page in pages if page)
    if not text:
        raise ValueError(
            f"No selectable text found in {pdf_path}; scanned PDFs need OCR first."
        )
    return text


def load_examples(input_dir: Path) -> list[dict[str, Any]]:
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input directory does not exist: {input_dir}")

    pdf_paths = sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() == ".pdf"
    )
    if not pdf_paths:
        raise ValueError(f"No PDF files found under: {input_dir}")

    examples = []
    for pdf_path in pdf_paths:
        label_filename = LABEL_FILENAME_BY_PDF.get(
            pdf_path.name.lower(), f"{pdf_path.stem}.json"
        )
        label_path = pdf_path.with_name(label_filename)
        if not label_path.is_file():
            raise FileNotFoundError(
                f"Missing JSON label for {pdf_path}: expected {label_path.name}"
            )

        try:
            target = json.loads(label_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON in {label_path}: {error}") from error
        if not isinstance(target, dict):
            raise ValueError(f"Expected a JSON object in label file: {label_path}")

        relative_pdf_path = pdf_path.relative_to(input_dir)
        relative_case_path = relative_pdf_path.parent
        case_id = (
            relative_case_path.as_posix()
            if relative_case_path != Path(".")
            else pdf_path.stem
        )
        examples.append(
            {
                "case_id": case_id,
                "document_type": (
                    UNSUPPORTED_LABEL if not target else label_path.stem
                ),
                "pdf_path": relative_pdf_path.as_posix(),
                "input_text": extract_pdf_text(pdf_path),
                "target_json": target,
            }
        )
    return examples


def split_by_case(
    examples: list[dict[str, Any]],
    validation_ratio: float,
    test_ratio: float,
    seed: int,
) -> dict[str, list[dict[str, Any]]]:
    if validation_ratio <= 0 or test_ratio <= 0:
        raise ValueError("Validation and test ratios must both be greater than zero.")
    if validation_ratio + test_ratio >= 1:
        raise ValueError("Validation and test ratios must add up to less than one.")

    case_ids = sorted({example["case_id"] for example in examples})
    if len(case_ids) < 3:
        raise ValueError(
            "At least three case folders are required to create train, validation, "
            "and test splits."
        )

    random.Random(seed).shuffle(case_ids)
    validation_count = max(1, round(len(case_ids) * validation_ratio))
    test_count = max(1, round(len(case_ids) * test_ratio))
    if validation_count + test_count >= len(case_ids):
        raise ValueError(
            "Not enough case folders for these split ratios; reduce the ratios "
            "or add more cases."
        )

    validation_cases = set(case_ids[:validation_count])
    test_cases = set(case_ids[validation_count : validation_count + test_count])
    train_cases = set(case_ids[validation_count + test_count :])

    return {
        "train": [example for example in examples if example["case_id"] in train_cases],
        "validation": [
            example for example in examples if example["case_id"] in validation_cases
        ],
        "test": [example for example in examples if example["case_id"] in test_cases],
    }


def write_splits(
    splits: dict[str, list[dict[str, Any]]], output_dir: Path
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for split_name, examples in splits.items():
        output_path = output_dir / f"{split_name}.jsonl"
        with output_path.open("w", encoding="utf-8") as output_file:
            for example in examples:
                output_file.write(
                    json.dumps(example, ensure_ascii=False, separators=(",", ":"))
                    + "\n"
                )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract PDF text and pair it with JSON labels for model training."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"Folder containing one case subfolder per case (default: {DEFAULT_INPUT_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Folder for JSONL splits (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument("--validation-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    try:
        examples = load_examples(args.input_dir)
        splits = split_by_case(
            examples,
            validation_ratio=args.validation_ratio,
            test_ratio=args.test_ratio,
            seed=args.seed,
        )
        write_splits(splits, args.output_dir)
    except (FileNotFoundError, NotADirectoryError, ValueError) as error:
        parser.error(str(error))

    for split_name, split_examples in splits.items():
        print(f"{split_name}: {len(split_examples)} examples")
    print(f"JSONL files written to: {args.output_dir}")


if __name__ == "__main__":
    main()
