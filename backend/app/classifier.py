"""Rozpoznawanie typu dokumentu na podstawie opisów klas z konfiguracji."""

from app.classes.registry import load_classes
from app.config import get_settings
from app.llm.client import complete_json

NONE_CLASS = "brak"

SYSTEM = (
    "Klasyfikujesz dokumenty PDF ze spraw odwoławczych przed Krajową Izbą Odwoławczą. "
    "Oceniasz wyłącznie treść (nazwa pliku może być myląca). Jeśli dokument nie pasuje "
    f'jednoznacznie do żadnej klasy (np. ogłoszenie, wyrok, decyzja, broszura), wybierz "{NONE_CLASS}". '
    'Zwróć JSON: {"class": <nazwa klasy>, "confidence": <0-1>, "reason": <jedno zdanie po polsku>}.'
)


def classify(text: str) -> dict:
    s = get_settings()
    classes = load_classes()
    catalog = "\n".join(
        f"- {c.name}: {c.description.strip()} Typowe słowa: {', '.join(c.keywords)}."
        for c in classes.values()
    )
    user = (
        f"Klasy:\n{catalog}\n- {NONE_CLASS}: dokument spoza powyższych klas.\n\n"
        f"Treść dokumentu (początek):\n{text[: s.classify_max_chars]}"
    )
    result = complete_json(SYSTEM, user)
    try:
        confidence = float(result.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    cls = result.get("class")
    if cls not in classes or confidence < s.min_confidence:
        cls = NONE_CLASS
    return {"class": cls, "confidence": confidence, "reason": result.get("reason", ""), "raw": result}
