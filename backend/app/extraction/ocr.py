"""OCR stron bez warstwy tekstowej: RapidOCR (ONNX, CPU, instalowany z pip)."""

from functools import lru_cache

import numpy as np
import pypdfium2 as pdfium


@lru_cache
def _engine():
    import logging

    from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

    from app.config import get_settings

    # rozpoznawanie: PP-OCRv5 dla alfabetu łacińskiego (polskie znaki diakrytyczne)
    engine = RapidOCR(params={
        "Global.log_level": "warning",
        "Rec.lang_type": LangRec.LATIN,
        "Rec.ocr_version": OCRVersion.PPOCRV5,
        "Rec.model_type": ModelType.MOBILE,
        "Rec.rec_batch_num": get_settings().ocr_rec_batch,
        **({"Rec.model_path": str(rec_model)} if (rec_model := get_settings().ocr_rec_model_path).is_file() else {}),
    })
    logging.getLogger("RapidOCR").setLevel(logging.WARNING)
    return engine


def ocr_page(page: pdfium.PdfPage, dpi: int | None = None) -> str:
    from app.config import get_settings

    dpi = dpi or get_settings().ocr_dpi
    image = np.array(page.render(scale=dpi / 72).to_pil().convert("RGB"))
    result = _engine()(image)
    return "\n".join(result.txts or ()) if result else ""
