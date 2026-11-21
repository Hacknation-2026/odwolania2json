"""YAML-only extraction (app/extraction/engine.py): a new class without any Python code."""

from pathlib import Path

import pytest
import yaml

from app.classes.registry import DocumentClass
from app.config import get_settings
from app.extraction import engine
from app.extraction.pdf_text import extract_pages
from app.extractor import extract

EXAMPLE = get_settings().config_dir / "examples" / "ogloszenie_bzp.yaml"
BZP_PDF = Path(__file__).resolve().parents[2] / "data" / "hacknation-2026" / "dane" / "negatywne" / "2025_BZP 00143067_01.pdf"


def _example_class() -> DocumentClass:
    return DocumentClass.model_validate(yaml.safe_load(EXAMPLE.read_text(encoding="utf-8")))


@pytest.mark.skipif(not BZP_PDF.exists(), reason="brak danych UZP")
def test_example_class_configured_only_in_yaml():
    text = "\n".join(p.text for p in extract_pages(BZP_PDF.read_bytes(), 2))
    data, _, method = extract(text, _example_class())
    assert method == "yaml"
    notice = data["ogloszenie_bzp"]
    assert notice["numer_ogloszenia"] == "2025/BZP00143067"  # normalize: bzp (format wzorców UZP)
    assert notice["data_ogloszenia"] == "2025-03-12"
    assert notice["rodzaj_zamowienia"] == "Usługi"
    assert notice["nazwa_zamowienia"].startswith("Utrzymanie w ciągłym ruchu urządzeń")
    assert notice["nazwa_zamowienia"].endswith("kompleksu wojskowego Celestynów")
    assert notice["identyfikator_postepowania"] == "ocds-148610-9893fd90-a029-43b1-9231-d18083d1416f"
    assert notice["zamawiajacy"] == {
        "nazwa": "26 Wojskowy Oddział Gospodarczy",
        "regon": "142917040",
        "miejscowosc": "Zegrze",
        "email": "jw4809.zp@ron.mil.pl",
    }


def test_labels_ignore_case_and_lost_diacritics():
    template = {"x": {"type": "string", "extract": {"after": ["Odwołujący:"], "value": "line"}}}
    assert engine.run(template, "ODWOLUJACY:\nMedicor S.A.") == {"x": "Medicor S.A."}


def test_lists_split_into_blocks_and_keywords():
    template = {
        "strony": [{
            "_split": r"^\d+\)",
            "nazwa": {"type": "string", "extract": {"pattern": r"^\d+\)\s*(.+)$"}},
            "nip": {"type": "string", "extract": {"after": ["NIP:?"], "value": "digits", "length": 10}},
        }],
        "powod": {"type": "integer", "extract": {"keywords": [{"id": 7, "pattern": "zaniechani\\w* odrzucenia"}, {"id": 1, "pattern": "odrzuc"}]}},
        "pelnomocnik": {"type": "integer", "extract": {"after": ["pełnomocnik"], "value": "flag", "default": 0}},
    }
    text = "1) Alfa sp. z o.o.\nNIP: 999-111-22-33\n2) Beta S.A.\nNIP 9990000000\nZaniechanie odrzucenia oferty"
    assert engine.run(template, text) == {
        "strony": [{"nazwa": "Alfa sp. z o.o.", "nip": "9991112233"}, {"nazwa": "Beta S.A.", "nip": "9990000000"}],
        "powod": 7,
        "pelnomocnik": 0,
    }


def test_yaml_fields_fill_gaps_left_by_builtin_rules():
    template = {"a": {"type": "string", "extract": {"after": ["A:"]}}, "b": {"type": "string"}}
    assert engine.merge({"a": None, "b": "z reguł"}, {"a": "z YAML", "b": None}, template) == {"a": "z YAML", "b": "z reguł"}


@pytest.mark.skipif(not BZP_PDF.exists(), reason="brak danych UZP")
def test_new_field_in_existing_class_only_in_yaml():
    """docs/DOKUMENTACJA.md, rozdz. 4: pole dopisane w YAML obok reguł wbudowanych."""
    from app.classes.registry import load_classes

    doc_class = load_classes()["przelew"].model_copy(deep=True)
    doc_class.output["przelew_bankowy"]["waluta"] = {
        "type": "string", "enum": ["PLN", "EUR"], "extract": {"pattern": r"\d[\d\s]*[.,]\d{2}\s*(PLN|EUR)\b"},
    }
    pdf = BZP_PDF.parents[1] / "przyklad_05" / "potwierdzenie_przelewu.pdf"
    data, _, method = extract("\n".join(p.text for p in extract_pages(pdf.read_bytes(), 1)), doc_class)
    assert method == "rules+yaml"
    assert (data["przelew_bankowy"]["waluta"], data["przelew_bankowy"]["kwota"]) == ("PLN", 17.0)
