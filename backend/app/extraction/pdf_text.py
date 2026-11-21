"""Wyciąganie tekstu z PDF (pypdfium2); strony bez warstwy tekstowej idą do OCR."""

from dataclasses import dataclass

import pypdfium2 as pdfium

from app.config import get_settings


@dataclass
class PageText:
    number: int
    text: str
    source: str  # "text" | "ocr" | "empty"


def extract_pages(pdf_bytes: bytes, max_pages: int) -> list[PageText]:
    settings = get_settings()
    pages: list[PageText] = []
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        for i in range(min(max_pages, len(pdf))):
            page = pdf[i]
            text = page.get_textpage().get_text_range().replace("\r\n", "\n").strip()
            if len(text) >= settings.ocr_min_chars or not settings.ocr_enabled:
                pages.append(PageText(i + 1, text, "text"))
                continue
            from app.extraction.ocr import ocr_page  # leniwie: model OCR ładuje się tylko dla skanów

            ocr_text = ocr_page(page)
            pages.append(PageText(i + 1, ocr_text, "ocr" if ocr_text else "empty"))
    finally:
        pdf.close()
    return pages
