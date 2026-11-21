"""OCR stron bez warstwy tekstowej: RapidOCR (ONNX, CPU, instalowany z pip)."""

from functools import lru_cache

import numpy as np
import pypdfium2 as pdfium


@lru_cache
def _engine():
    from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

    # rozpoznawanie: PP-OCRv5 dla alfabetu łacińskiego (polskie znaki diakrytyczne)
    return RapidOCR(params={
        "Rec.lang_type": LangRec.LATIN,
        "Rec.ocr_version": OCRVersion.PPOCRV5,
        "Rec.model_type": ModelType.MOBILE,
    })


def ocr_page(page: pdfium.PdfPage, dpi: int = 200) -> str:
    image = np.array(page.render(scale=dpi / 72).to_pil().convert("RGB"))
    result = _engine()(image)
    return "\n".join(result.txts or ()) if result else ""
