"""Field extraction for a recognised document class.

Default: local, deterministic rules (app/extraction/rules.py) - no API calls.
A class from YAML that has no rules uses the LLM only when LLM_API_KEY is set;
otherwise it gets its output template filled with nulls.
"""

from app.classes.registry import DocumentClass
from app.config import get_settings
from app.extraction import rules
from app.schema import conform, field_guide, to_json_schema

RULES = {
    "odwolanie": rules.extract_odwolanie,
    "pelnomocnictwo": rules.extract_pelnomocnictwo,
    "przelew": rules.extract_przelew,
}

SYSTEM = (
    "Wyodrębniasz dane z polskich dokumentów prawnych do JSON zgodnego ze schematem. "
    "Przepisuj wartości dokładnie tak, jak występują w tekście (nazwy, numery). "
    "Jeśli informacji nie ma w tekście, wpisz null. Nie zgaduj i nie wymyślaj danych."
)


def extract(text: str, doc_class: DocumentClass) -> tuple[dict, dict | None, str]:
    """Returns (result shaped like the class template, raw extractor output, method)."""
    if doc_class.name in RULES:
        raw = RULES[doc_class.name](text)
        return conform(doc_class.output, raw), raw, "rules"
    if get_settings().llm_api_key:
        raw = _extract_llm(text, doc_class)
        return conform(doc_class.output, raw), raw, "llm"
    return conform(doc_class.output, {}), None, "none"


def _extract_llm(text: str, doc_class: DocumentClass) -> dict:
    from app.llm.client import complete_json  # only imported when an API key is configured

    guide = "\n".join(field_guide(doc_class.output))
    user = (
        f"Typ dokumentu: {doc_class.name}\n{doc_class.instructions.strip()}\n\n"
        f"Pola do wyodrębnienia:\n{guide}\n\nTreść dokumentu:\n{text}"
    )
    return complete_json(SYSTEM, user, json_schema=to_json_schema(doc_class.output))
