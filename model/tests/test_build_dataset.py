import json
import tempfile
import unittest
from pathlib import Path

import pymupdf

from src.build_dataset import load_examples, split_by_case, write_splits


def create_pdf(path: Path, text: str) -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


class BuildDatasetTests(unittest.TestCase):
    def test_default_split_assigns_40_10_10_case_folders(self) -> None:
        examples = [
            {"case_id": f"case_{case_number:02}", "document": document_number}
            for case_number in range(60)
            for document_number in range(3)
        ]

        splits = split_by_case(examples, seed=42)
        case_counts = {
            split_name: len({example["case_id"] for example in split_examples})
            for split_name, split_examples in splits.items()
        }

        self.assertEqual(
            case_counts,
            {"train": 40, "validation": 10, "test": 10},
        )
        self.assertEqual(
            {name: len(rows) for name, rows in splits.items()},
            {"train": 120, "validation": 30, "test": 30},
        )

    def test_pairs_documents_and_splits_by_case(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_dir = root / "raw"
            output_dir = root / "processed"

            for case_number in range(6):
                case_dir = input_dir / f"case_{case_number:02}"
                case_dir.mkdir(parents=True)

                create_pdf(case_dir / "odwolanie.pdf", "Appeal document text")
                (case_dir / "odwolanie.json").write_text(
                    json.dumps({"tytul": "Zażółć gęślą jaźń"}, ensure_ascii=False),
                    encoding="utf-8",
                )

                create_pdf(
                    case_dir / "potwierdzenie_przelewu.pdf", "Payment confirmation"
                )
                (case_dir / "przelew.json").write_text(
                    json.dumps({"kwota": 200.0}), encoding="utf-8"
                )

            negative_case = input_dir / "case_negative"
            negative_case.mkdir(parents=True)
            create_pdf(negative_case / "notice.pdf", "Unrelated document")
            (negative_case / "notice.json").write_text("{}", encoding="utf-8")

            examples = load_examples(input_dir)
            self.assertEqual(len(examples), 13)
            payment_example = next(
                example
                for example in examples
                if example["pdf_path"].endswith("potwierdzenie_przelewu.pdf")
            )
            self.assertEqual(payment_example["document_type"], "przelew")
            self.assertEqual(payment_example["target_json"], {"kwota": 200.0})
            self.assertIn("Payment confirmation", payment_example["input_text"])
            negative_example = next(
                example
                for example in examples
                if example["pdf_path"].endswith("notice.pdf")
            )
            self.assertEqual(negative_example["document_type"], "__unsupported__")

            splits = split_by_case(examples, 0.1, 0.1, seed=7)
            cases_by_split = {
                split_name: {example["case_id"] for example in split_examples}
                for split_name, split_examples in splits.items()
            }
            self.assertEqual(sum(map(len, splits.values())), len(examples))
            self.assertFalse(cases_by_split["train"] & cases_by_split["validation"])
            self.assertFalse(cases_by_split["train"] & cases_by_split["test"])
            self.assertFalse(cases_by_split["validation"] & cases_by_split["test"])

            write_splits(splits, output_dir)
            train_rows = [
                json.loads(line)
                for line in (output_dir / "train.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            self.assertTrue(train_rows)
            self.assertIn(
                "Zażółć gęślą jaźń",
                json.dumps(train_rows, ensure_ascii=False),
            )


if __name__ == "__main__":
    unittest.main()
