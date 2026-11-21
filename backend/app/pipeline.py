"""PDF -> tekst (+OCR) -> klasyfikacja (lokalny model) -> ekstrakcja (lokalne reguły) -> JSON (+ ślad)."""

import time

from app.classes.registry import load_classes
from app.classifier import classify
from app.config import get_settings
from app.extraction.pdf_text import extract_pages
from app.extractor import extract


def _join(pages) -> str:
    return "\n\n".join(p.text for p in pages if p.text)


def process_pdf(pdf_bytes: bytes, filename: str = "") -> dict:
    """Zwraca {document_type, data, trace}. `data` = None dla dokumentów spoza klas (pusty JSON)."""
    started = time.perf_counter()
    classes = load_classes()
    # najpierw tylko strony potrzebne do klasyfikacji - OCR skanów jest najdroższym krokiem
    pages = extract_pages(pdf_bytes, get_settings().classify_max_pages)
    classification = classify(pages)
    doc_class = classes.get(classification["class"])

    data, raw, method = None, None, None
    if doc_class:
        if doc_class.max_pages > len(pages):
            pages += extract_pages(pdf_bytes, doc_class.max_pages, start=len(pages))
        data, raw, method = extract(_join(pages[: doc_class.max_pages]), doc_class)

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
