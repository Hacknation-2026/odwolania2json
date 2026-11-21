"""Document-type recognition with the local model (app/text_model.py); no API calls.

The model looks at the beginning of the document (first page, more pages if it is short),
which is where the document type shows: header, title, parties, bank form.
"""

from functools import lru_cache

import joblib

from app.classes.registry import load_classes
from app.config import get_settings
from app.text_model import TextModel

NONE_CLASS = "brak"


def classifier_text(pages) -> str:
    """Text the model sees - shared by training and inference so both see the same input."""
    s = get_settings()
    parts: list[str] = []
    for page in pages[: s.classify_max_pages]:
        if page.text:
            parts.append(page.text)
        if sum(map(len, parts)) >= s.classify_min_chars:
            break
    return "\n\n".join(parts)


@lru_cache
def load_model() -> TextModel:
    path = get_settings().classifier_model_path
    if not path.is_file():
        raise FileNotFoundError(f"Brak modelu klasyfikatora: {path} - uruchom train.bat")
    return TextModel.from_artifact(joblib.load(path))


def classify(pages) -> dict:
    """Returns {class, confidence, reason, raw}; class = NONE_CLASS for unsupported documents."""
    text = classifier_text(pages)
    if not text.strip():
        return {"class": NONE_CLASS, "confidence": 0.0, "reason": "Brak tekstu w dokumencie.", "raw": None}

    p = load_model().predict(text, get_settings().min_confidence)
    classes = load_classes()
    if p.label is None:
        reason = "Dokument spoza obsługiwanych klas lub zbyt niska pewność."
    elif p.label not in classes:  # model trained for a class whose YAML was removed
        reason = f"Klasa '{p.label}' nie ma pliku YAML w config/classes."
    else:
        reason = f"Rozpoznano lokalnym modelem jako: {classes[p.label].label or p.label}."
    return {
        "class": p.label if p.label in classes else NONE_CLASS,
        "confidence": round(p.confidence, 3),
        "reason": f"{reason} Najbardziej podobny przykład treningowy: {p.nearest_example} "
        f"(podobieństwo {p.nearest_similarity:.2f}).",
        "raw": {"probabilities": p.probabilities, "nearest_example": p.nearest_example},
    }
