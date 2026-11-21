"""PDF -> tekst (+OCR) -> klasyfikacja -> ekstrakcja -> JSON (+ ślad przetwarzania)."""

import time

from app.classes.registry import load_classes
from app.classifier import classify
from app.config import get_settings
from app.extraction.pdf_text import extract_pages
from app.extractor import extract


def _join(pages) -> str:
    return "\n\n".join(f"[strona {p.number}]\n{p.text}" for p in pages)


def process_pdf(pdf_bytes: bytes, filename: str = "") -> dict:
    """Zwraca {document_type, data, trace}. `data` = None dla dokumentów spoza klas (pusty JSON)."""
    started = time.perf_counter()
    classes = load_classes()
    max_pages = max([get_settings().classify_pages, *(c.max_pages for c in classes.values())])
    pages = extract_pages(pdf_bytes, max_pages)

    classification = classify(_join(pages[: get_settings().classify_pages]))
    doc_class = classes.get(classification["class"])

    data, raw = None, None
    if doc_class:
        data, raw = extract(_join(pages[: doc_class.max_pages]), doc_class)

    return {
        "file": filename,
        "document_type": classification["class"],
        "data": data,
        "trace": {  # transparentność: skąd wziął się wynik
            "classification": classification,
            "pages": [{"number": p.number, "source": p.source, "chars": len(p.text)} for p in pages],
            "llm_raw_output": raw,
            "seconds": round(time.perf_counter() - started, 2),
        },
    }
