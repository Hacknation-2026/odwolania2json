from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Any

import pymupdf

try:
    from .classifier import UNSUPPORTED_LABEL
except ImportError:
    from classifier import UNSUPPORTED_LABEL


MODEL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = MODEL_DIR / "data" / "raw_augmented"
DEFAULT_OUTPUT_DIR = MODEL_DIR / "data" / "processed"
DEFAULT_VALIDATION_RATIO = 1 / 6
DEFAULT_TEST_RATIO = 1 / 6
DEFAULT_AUGMENTATION_RATIO = 0.05
AUGMENTED_CASE_SUFFIX = re.compile(r"^(?P<base>.+)_(?P<variant>aug[12])$", re.I)
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


def case_family(case_path: Path) -> tuple[str, str]:
    match = AUGMENTED_CASE_SUFFIX.fullmatch(case_path.name)
    if not match:
        return case_path.as_posix(), "regular"
    family_path = case_path.with_name(match.group("base"))
    return family_path.as_posix(), match.group("variant").lower()


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
        case_group_id, case_variant = case_family(Path(case_id))
        examples.append(
            {
                "case_id": case_id,
                "case_group_id": case_group_id,
                "case_variant": case_variant,
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
    validation_ratio: float = DEFAULT_VALIDATION_RATIO,
    test_ratio: float = DEFAULT_TEST_RATIO,
    seed: int = 42,
    augmentation_ratio: float = DEFAULT_AUGMENTATION_RATIO,
) -> dict[str, list[dict[str, Any]]]:
    if validation_ratio <= 0 or test_ratio <= 0:
        raise ValueError("Validation and test ratios must both be greater than zero.")
    if validation_ratio + test_ratio >= 1:
        raise ValueError("Validation and test ratios must add up to less than one.")
    if not 0 <= augmentation_ratio <= 1:
        raise ValueError("Augmentation ratio must be between 0 and 1.")

    case_group_ids = sorted(
        {example.get("case_group_id", example["case_id"]) for example in examples}
    )
    if len(case_group_ids) < 3:
        raise ValueError(
            "At least three case folders are required to create train, validation, "
            "and test splits."
        )

    rng = random.Random(seed)
    rng.shuffle(case_group_ids)
    validation_count = max(1, round(len(case_group_ids) * validation_ratio))
    test_count = max(1, round(len(case_group_ids) * test_ratio))
    if validation_count + test_count >= len(case_group_ids):
        raise ValueError(
            "Not enough case folders for these split ratios; reduce the ratios "
            "or add more cases."
        )

    validation_cases = set(case_group_ids[:validation_count])
    test_cases = set(
        case_group_ids[validation_count : validation_count + test_count]
    )
    train_cases = set(case_group_ids[validation_count + test_count :])

    def split_examples(group_ids: set[str]) -> list[dict[str, Any]]:
        augmented_folders_by_group: dict[str, set[str]] = {}
        for example in examples:
            group_id = example.get("case_group_id", example["case_id"])
            if (
                group_id in group_ids
                and example.get("case_variant", "regular") != "regular"
            ):
                augmented_folders_by_group.setdefault(group_id, set()).add(
                    example["case_id"]
                )

        augmented_folders = {
            case_id
            for case_ids in augmented_folders_by_group.values()
            for case_id in case_ids
        }
        augmented_folder_count = round(len(augmented_folders) * augmentation_ratio)
        group_options = list(augmented_folders_by_group.items())
        rng.shuffle(group_options)

        selected_augmented_folders = set()
        for _, case_ids in group_options:
            if len(selected_augmented_folders) >= augmented_folder_count:
                break
            options = sorted(case_ids)
            rng.shuffle(options)
            selected_augmented_folders.add(options[0])

        remaining_folders = list(augmented_folders - selected_augmented_folders)
        rng.shuffle(remaining_folders)
        selected_augmented_folders.update(
            remaining_folders[
                : augmented_folder_count - len(selected_augmented_folders)
            ]
        )

        return [
            example
            for example in examples
            if example.get("case_group_id", example["case_id"]) in group_ids
            and (
                example.get("case_variant", "regular") == "regular"
                or example["case_id"] in selected_augmented_folders
            )
        ]

    return {
        "train": split_examples(train_cases),
        "validation": split_examples(validation_cases),
        "test": split_examples(test_cases),
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
    parser.add_argument(
        "--validation-ratio", type=float, default=DEFAULT_VALIDATION_RATIO
    )
    parser.add_argument("--test-ratio", type=float, default=DEFAULT_TEST_RATIO)
    parser.add_argument(
        "--augmentation-ratio",
        type=float,
        default=DEFAULT_AUGMENTATION_RATIO,
        help="Fraction of augmented folders included within each split (0 to 1).",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    try:
        examples = load_examples(args.input_dir)
        splits = split_by_case(
            examples,
            validation_ratio=args.validation_ratio,
            test_ratio=args.test_ratio,
            seed=args.seed,
            augmentation_ratio=args.augmentation_ratio,
        )
        write_splits(splits, args.output_dir)
    except (FileNotFoundError, NotADirectoryError, ValueError) as error:
        parser.error(str(error))

    for split_name, split_examples in splits.items():
        print(f"{split_name}: {len(split_examples)} examples")
    print(f"JSONL files written to: {args.output_dir}")


if __name__ == "__main__":
    main()
