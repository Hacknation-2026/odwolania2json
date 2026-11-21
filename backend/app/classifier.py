"""Rozpoznawanie typu dokumentu na podstawie opisów klas z konfiguracji."""

import unicodedata

from app.classes.registry import load_classes
from app.config import get_settings
from app.llm.client import complete_json

NONE_CLASS = "brak"

SYSTEM = (
    "Klasyfikujesz dokumenty PDF ze spraw odwoławczych przed Krajową Izbą Odwoławczą. "
    "Oceniasz wyłącznie treść (nazwa pliku może być myląca). Jeśli dokument nie pasuje "
    f'jednoznacznie do żadnej klasy (np. ogłoszenie, wyrok, decyzja, broszura), wybierz "{NONE_CLASS}". '
    'Zwróć JSON: {"class": <dokładnie jedna nazwa z listy>, "confidence": <0-1>, "reason": <jedno zdanie po polsku>}.'
)


def _key(name: str) -> str:
    """'Odwołanie ' -> 'odwolanie' (bez polskich znaków, wielkości liter i spacji)."""
    name = name.replace("ł", "l").replace("Ł", "L")
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return ascii_name.strip().lower().replace(" ", "_")


def classify(text: str) -> dict:
    s = get_settings()
    classes = load_classes()
    names = [*classes, NONE_CLASS]
    catalog = "\n".join(
        f"- {c.name}: {c.description.strip()} Typowe słowa: {', '.join(c.keywords)}."
        for c in classes.values()
    )
    user = (
        f"Klasy:\n{catalog}\n- {NONE_CLASS}: dokument spoza powyższych klas.\n"
        f"Dozwolone wartości pola class: {', '.join(names)}.\n\n"
        f"Treść dokumentu (początek):\n{text[: s.classify_max_chars]}"
    )
    schema = {
        "type": "object",
        "properties": {
            "class": {"type": "string", "enum": names},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["class", "confidence", "reason"],
        "additionalProperties": False,
    }
    result = complete_json(SYSTEM, user, json_schema=schema)
    try:
        confidence = float(result.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    by_key = {_key(n): n for n in classes}
    cls = by_key.get(_key(str(result.get("class", ""))))
    if cls is None or confidence < s.min_confidence:
        cls = NONE_CLASS
    return {"class": cls, "confidence": confidence, "reason": result.get("reason", ""), "raw": result}
