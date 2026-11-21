"""Ekstrakcja pól zdefiniowanych w szablonie klasy dokumentu."""

from app.classes.registry import DocumentClass
from app.llm.client import complete_json
from app.schema import conform, field_guide, to_json_schema

SYSTEM = (
    "Wyodrębniasz dane z polskich dokumentów prawnych do JSON zgodnego ze schematem. "
    "Przepisuj wartości dokładnie tak, jak występują w tekście (nazwy, numery). "
    "Jeśli informacji nie ma w tekście, wpisz null. Nie zgaduj i nie wymyślaj danych."
)


def extract(text: str, doc_class: DocumentClass) -> tuple[dict, dict]:
    """Zwraca (wynik dopasowany do szablonu, surowa odpowiedź LLM)."""
    guide = "\n".join(field_guide(doc_class.output))
    user = (
        f"Typ dokumentu: {doc_class.name}\n{doc_class.instructions.strip()}\n\n"
        f"Pola do wyodrębnienia:\n{guide}\n\nTreść dokumentu:\n{text}"
    )
    raw = complete_json(SYSTEM, user, json_schema=to_json_schema(doc_class.output))
    return conform(doc_class.output, raw), raw
