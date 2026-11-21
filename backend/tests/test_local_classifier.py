from pathlib import Path

import pytest

from app.classifier import NONE_CLASS, classify
from app.config import get_settings
from app.extraction.pdf_text import PageText, extract_pages
from app.text_model import normalize_text

DANE = Path(__file__).resolve().parents[2] / "data" / "hacknation-2026" / "dane"
EXPECTED = {"odwolanie": "odwolanie", "pelnomocnictwo": "pelnomocnictwo", "potwierdzenie_przelewu": "przelew"}

needs_model = pytest.mark.skipif(
    not DANE.exists() or not get_settings().classifier_model_path.exists(),
    reason="brak danych UZP lub modelu klasyfikatora",
)


def _classify(pdf: Path) -> str:
    return classify(extract_pages(pdf.read_bytes(), get_settings().classify_max_pages))["class"]


def test_normalize_text_ignores_diacritics_lost_by_ocr():
    assert normalize_text("ODWOŁANIE  Odwołujący") == normalize_text("ODWOLANIE Odwolujacy")


@needs_model
@pytest.mark.parametrize("case", ["przyklad_01", "przyklad_30", "przyklad_60"])
def test_known_documents(case):
    for pdf in (DANE / case).glob("*.pdf"):
        if pdf.stem in EXPECTED:
            assert _classify(pdf) == EXPECTED[pdf.stem], pdf


@needs_model
def test_negatives_are_rejected():
    for pdf in ["przyklad_04/2025_S 112-383751.pdf", "negatywne/KIO_KIO 2617-21.pdf"]:
        assert _classify(DANE / pdf) == NONE_CLASS, pdf


@needs_model
def test_ocr_style_text_without_diacritics():
    text = (DANE / "przyklad_01" / "odwolanie.pdf").read_bytes()
    page = extract_pages(text, 1)[0]
    stripped = normalize_text(page.text)  # simulates OCR that lost every Polish letter
    assert classify([PageText(1, stripped, "ocr")])["class"] == "odwolanie"


def test_empty_document_is_none():
    assert classify([PageText(1, "", "empty")])["class"] == NONE_CLASS
