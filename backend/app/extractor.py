"""Field extraction for a recognised document class - everything is driven by the class YAML.

1. `rules: <name>` in the YAML selects built-in Python rules (BUILTIN_RULES) - used for the
   three UZP classes, where hand-written rules give the best F1.
2. `extract:` specs on template fields (app/extraction/engine.py) are applied on top: they fill
   fields the built-in rules left empty, or replace them with `override: true`. A new class can
   be configured with these specs alone - no code changes.
3. Fields still empty may be filled by an LLM, but only when LLM_API_KEY is set (optional).
The result always has exactly the shape of the YAML template (app/schema.py: conform).
"""

from app.classes.registry import DocumentClass
from app.config import get_settings
from app.extraction import engine, rules
from app.schema import conform, field_guide, to_json_schema

BUILTIN_RULES = {
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
    template = doc_class.output
    methods, raw = [], None
    if doc_class.rules:
        if doc_class.rules not in BUILTIN_RULES:
            raise ValueError(f"Klasa {doc_class.name}: nieznane reguły '{doc_class.rules}' (dostępne: {', '.join(BUILTIN_RULES)})")
        raw = BUILTIN_RULES[doc_class.rules](text, doc_class)
        methods.append("rules")
    if engine.has_rules(template):
        yaml_result = engine.run(template, text)
        raw = engine.merge(raw, yaml_result, template) if raw is not None else yaml_result
        methods.append("yaml")
    if raw is None and get_settings().llm_api_key:
        raw = _extract_llm(text, doc_class)
        methods.append("llm")
    return conform(template, raw or {}), raw, "+".join(methods) or "none"


def _extract_llm(text: str, doc_class: DocumentClass) -> dict:
    from app.llm.client import complete_json  # only imported when an API key is configured

    guide = "\n".join(field_guide(doc_class.output))
    user = (
        f"Typ dokumentu: {doc_class.name}\n{doc_class.instructions.strip()}\n\n"
        f"Pola do wyodrębnienia:\n{guide}\n\nTreść dokumentu:\n{text}"
    )
    return complete_json(SYSTEM, user, json_schema=to_json_schema(doc_class.output))
