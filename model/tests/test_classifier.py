import json
import tempfile
import unittest
from pathlib import Path

import pymupdf

from src.classifier import DocumentClassifier
from src.predict import load_classifier, pdf_paths, predict, write_json_outputs
from src.train import train


class DocumentClassifierTests(unittest.TestCase):
    def test_learns_document_type_from_text_not_file_name(self) -> None:
        texts = [
            "ODWOŁANIE Prezes Krajowej Izby Odwoławczej Zamawiający Odwołujący zarzuty",
            "O D W O Ł A N I E do Krajowej Izby Odwoławczej, zarzut i wniosek",
            "PEŁNOMOCNICTWO Mocodawca ustanawia pełnomocnika do reprezentacji",
            "Pełnomocnik umocowany do składania pism przed Krajową Izbą Odwoławczą",
            "Potwierdzenie przelewu Kwota operacji Data transakcji rachunek odbiorcy",
            "Polecenie przelewu Płatnik Beneficjent Numer referencyjny Kwota",
        ]
        labels = [
            "odwolanie",
            "odwolanie",
            "pelnomocnictwo",
            "pelnomocnictwo",
            "przelew",
            "przelew",
        ]
        classifier = DocumentClassifier.fit(texts, labels, min_confidence=0.0)

        with tempfile.TemporaryDirectory() as temporary_directory:
            pdf_path = Path(temporary_directory) / "random-name.pdf"
            document = pymupdf.open()
            page = document.new_page()
            page.insert_text((72, 72), texts[0])
            document.save(pdf_path)
            document.close()
            results = predict(
                [pdf_path],
                classifier,
            )

        self.assertEqual(results[0]["document_type"], "odwolanie")

    def test_empty_annotation_trains_explicit_unsupported_class(self) -> None:
        classifier = DocumentClassifier.fit(
            [
                "ODWOŁANIE do Krajowej Izby Odwoławczej",
                "Pełnomocnictwo dla radcy prawnego",
                "instrukcja obsługi urządzenia biurowego",
                "regulamin biblioteki i zasady wypożyczania",
            ],
            ["odwolanie", "odwolanie", "__unsupported__", "__unsupported__"],
            min_confidence=0.0,
        )

        result = classifier.classify("regulamin biblioteki i wypożyczania")

        self.assertIsNone(result.document_type)
        self.assertEqual(result.status, "unsupported")

    def test_low_confidence_prediction_is_not_forced_into_a_known_type(self) -> None:
        classifier = DocumentClassifier.fit(
            [
                "ODWOŁANIE Prezes Krajowej Izby Odwoławczej",
                "Odwołujący wnosi odwołanie do Izby",
                "PEŁNOMOCNICTWO Mocodawca ustanawia pełnomocnika",
                "Pełnomocnik umocowany do reprezentacji",
            ],
            ["odwolanie", "odwolanie", "pelnomocnictwo", "pelnomocnictwo"],
            min_confidence=1.0,
        )

        result = classifier.classify("Opis techniczny urządzenia i instrukcja obsługi")

        self.assertIsNone(result.document_type)
        self.assertEqual(result.status, "uncertain")

    def test_unrelated_text_is_rejected_by_example_similarity(self) -> None:
        classifier = DocumentClassifier.fit(
            [
                "ODWOŁANIE Prezes Krajowej Izby Odwoławczej Zamawiający Odwołujący",
                "O D W O Ł A N I E do Krajowej Izby Odwoławczej, zarzut i wniosek",
                "PEŁNOMOCNICTWO Mocodawca ustanawia pełnomocnika do reprezentacji",
                "Pełnomocnik umocowany do składania pism przed Krajową Izbą Odwoławczą",
                "Potwierdzenie przelewu Kwota operacji Data transakcji rachunek odbiorcy",
                "Polecenie przelewu Płatnik Beneficjent Numer referencyjny Kwota",
            ],
            [
                "odwolanie",
                "odwolanie",
                "pelnomocnictwo",
                "pelnomocnictwo",
                "przelew",
                "przelew",
            ],
            min_confidence=0.0,
        )

        result = classifier.classify(
            "Faktura VAT za zakup materiałów biurowych, termin płatności 14 dni."
        )

        self.assertIsNone(result.document_type)
        self.assertEqual(result.status, "uncertain")
        self.assertLess(result.nearest_example_similarity, 0.2)

    def test_training_saves_loadable_model_and_prints_test_score(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            data_dir = root / "processed"
            data_dir.mkdir()
            rows = {
                "train": [
                    ('"ODWOŁANIE Krajowa Izba Odwoławcza"', '"odwolanie"'),
                    ('"O D W O Ł A N I E zarzut wniosek"', '"odwolanie"'),
                    ('"Pełnomocnictwo pełnomocnik mocodawca"', '"pelnomocnictwo"'),
                    ('"Pełnomocnik umocowany do reprezentacji"', '"pelnomocnictwo"'),
                    ('"Potwierdzenie przelewu kwota rachunek"', '"przelew"'),
                    ('"Polecenie przelewu płatnik beneficjent"', '"przelew"'),
                ],
                "test": [
                    ('"ODWOŁANIE Izba Odwoławcza"', '"odwolanie"'),
                    ('"Pełnomocnictwo mocodawca"', '"pelnomocnictwo"'),
                    ('"Przelew kwota rachunek"', '"przelew"'),
                ],
            }
            for split, examples in rows.items():
                lines = [
                    json.dumps(
                        {
                            "input_text": json.loads(text),
                            "document_type": json.loads(label),
                        }
                    )
                    for text, label in examples
                ]
                (data_dir / f"{split}.jsonl").write_text(
                    "\n".join(lines), encoding="utf-8"
                )

            model_path = root / "model.joblib"
            train(data_dir, model_path, min_confidence=0.0)

            self.assertEqual(len(load_classifier(model_path).model.classes_), 3)

    def test_pdf_paths_rejects_non_pdf_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            text_file = Path(temporary_directory) / "document.txt"
            text_file.touch()
            with self.assertRaisesRegex(ValueError, "Expected a PDF"):
                pdf_paths([text_file])

    def test_writes_json_outputs_with_input_folder_structure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_dir = root / "input"
            case_dir = input_dir / "case1"
            case_dir.mkdir(parents=True)
            appeal_pdf = case_dir / "random-name.pdf"
            unsupported_pdf = case_dir / "attachment.pdf"
            appeal_pdf.touch()
            unsupported_pdf.touch()
            output_dir = root / "output"

            destinations = write_json_outputs(
                [
                    {"file": str(appeal_pdf), "json": {"OdwolanieKIO": {}}},
                    {"file": str(unsupported_pdf), "json": {}},
                ],
                [input_dir],
                output_dir,
            )

            self.assertEqual(
                destinations,
                [
                    output_dir / "case1" / "random-name.json",
                    output_dir / "case1" / "attachment.json",
                ],
            )
            self.assertEqual(
                json.loads(destinations[0].read_text(encoding="utf-8")),
                {"OdwolanieKIO": {}},
            )
            self.assertEqual(
                json.loads(destinations[1].read_text(encoding="utf-8")),
                {},
            )


if __name__ == "__main__":
    unittest.main()
