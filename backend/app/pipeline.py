"""PDF -> tekst (+OCR) -> klasyfikacja (lokalny model) -> ekstrakcja (lokalne reguły) -> JSON (+ ślad)."""

import time
from collections.abc import Callable

from app.classes.registry import load_classes
from app.classifier import classify
from app.config import get_settings
from app.extraction.ocr_fix import fix_text
from app.extraction.pdf_text import PageText, extract_pages
from app.extractor import extract


def _join(pages) -> str:
    return "\n\n".join(p.text for p in pages if p.text)


def process_pdf(pdf_bytes: bytes, filename: str = "") -> dict:
    """Zwraca {document_type, data, trace}. `data` = None dla dokumentów spoza klas (pusty JSON)."""
    return process_document(lambda end, start=0: extract_pages(pdf_bytes, end, start), filename)


def _repaired(pages: list[PageText]) -> list[PageText]:
    """Strony z OCR: przywrócenie polskich znaków zgubionych przez OCR (app/extraction/ocr_fix.py)."""
    return [PageText(p.number, fix_text(p.text), p.source) if p.source == "ocr" else p for p in pages]


def _classification_pages(load_pages: Callable[..., list]) -> list:
    """Pages one by one, only as many as the classifier reads (classifier_text stops at classify_min_chars):
    a scanned page costs seconds of OCR, so page 2-3 is read only when page 1 has too little text."""
    s = get_settings()
    pages: list = []
    while len(pages) < s.classify_max_pages:
        more = load_pages(len(pages) + 1, len(pages))
        if not more:  # end of document
            break
        pages += more
        if sum(len(p.text) for p in pages if p.text) >= s.classify_min_chars:
            break
    return pages


def process_document(load_pages: Callable[..., list], filename: str = "") -> dict:
    """Jak process_pdf, ale strony dostarcza load_pages(end, start) - np. z cache w benchmarku."""
    started = time.perf_counter()
    raw_loader = load_pages
    load_pages = lambda end, start=0: _repaired(raw_loader(end, start))  # noqa: E731
    classes = load_classes()
    # najpierw tylko strony potrzebne do klasyfikacji - OCR skanów jest najdroższym krokiem
    pages = _classification_pages(load_pages)
    classification = classify(pages)
    doc_class = classes.get(classification["class"])

    data, raw, method = None, None, None
    if doc_class:
        limit = doc_class.max_pages
        if doc_class.max_ocr_pages and any(p.source == "ocr" for p in pages):  # scan: OCR is the costly step
            limit = min(limit, doc_class.max_ocr_pages)
        if limit > len(pages):
            pages += load_pages(limit, len(pages))
        data, raw, method = extract(_join(pages[:limit]), doc_class)

    return {
        "file": filename,
        "document_type": classification["class"],
        "data": data,
        "trace": {  # transparentność: skąd wziął się wynik
            "classification": classification,
            "extraction": {"method": method, "raw_output": raw},
            "pages": [{"number": p.number, "source": p.source, "chars": len(p.text)} for p in pages],
            "seconds": round(time.perf_counter() - started, 2),
        },
    }
