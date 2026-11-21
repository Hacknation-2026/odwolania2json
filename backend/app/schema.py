"""Szablon wyjścia z YAML -> JSON Schema dla LLM, instrukcja pól i dopasowanie odpowiedzi do szablonu.

Format szablonu:
  - liść:   {type: string|integer|number|date, description, [enum], [normalize], [dictionary], [derive]}
  - obiekt: mapa nazwa -> węzeł
  - tablica: lista z jednym węzłem (szablon elementu)
Klucze zaczynające się od "_" (np. _section, _split) i "extract" w liściach to konfiguracja
ekstrakcji (app/extraction/engine.py) - nie trafiają do wyniku.
"""

from typing import Any

from app.classes.registry import load_dictionaries
from app.normalizers import NORMALIZERS, to_date, to_number

JSON_TYPES = {"string": "string", "date": "string", "integer": "integer", "number": "number"}


def is_leaf(node: Any) -> bool:
    return isinstance(node, dict) and isinstance(node.get("type"), str)


def _dictionary(name: str) -> dict:
    return load_dictionaries()[name]


# ---------- JSON Schema dla LLM ----------

def to_json_schema(node: Any) -> dict:
    if is_leaf(node):
        schema: dict = {"type": [JSON_TYPES[node["type"]], "null"]}
        desc = node.get("description", "")
        if node.get("type") == "date":
            desc += " Format YYYY-MM-DD."
        if dict_name := node.get("dictionary"):
            d = _dictionary(dict_name)
            schema["enum"] = [*d.keys(), None]
            desc += " " + ", ".join(f"{k}={v}" for k, v in d.items())
        elif "enum" in node:
            schema["enum"] = [*node["enum"], None]
        schema["description"] = desc.strip()
        return schema
    if isinstance(node, list):
        return {"type": "array", "items": to_json_schema(node[0])}
    props = {
        k: to_json_schema(v)
        for k, v in node.items()
        if not k.startswith("_") and not (is_leaf(v) and "derive" in v)
    }
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def field_guide(node: Any, path: str = "") -> list[str]:
    """Czytelna lista pól z opisami do promptu."""
    if is_leaf(node):
        if "derive" in node:
            return []
        schema = to_json_schema(node)
        return [f"- {path} ({node['type']}): {schema['description']}"]
    if isinstance(node, list):
        return field_guide(node[0], f"{path}[]")
    return [
        line
        for k, v in node.items()
        if not k.startswith("_")
        for line in field_guide(v, f"{path}.{k}" if path else k)
    ]


# ---------- dopasowanie odpowiedzi LLM do szablonu ----------

def _cast_leaf(node: dict, value: Any) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    t = node["type"]
    try:
        if t == "integer":
            value = int(to_number(value))
        elif t == "number":
            value = to_number(value)
        elif t == "date":
            value = to_date(str(value))
        else:
            value = str(value).strip()
    except (TypeError, ValueError):
        return None
    if value is not None and (norm := node.get("normalize")):
        value = NORMALIZERS[norm](str(value))
    allowed = list(_dictionary(node["dictionary"])) if "dictionary" in node else node.get("enum")
    if allowed is not None and value not in allowed:
        return None
    return value


def conform(node: Any, value: Any) -> Any:
    """Zwraca wartość o dokładnie takiej strukturze i kolejności kluczy jak szablon."""
    if is_leaf(node):
        return _cast_leaf(node, value)
    if isinstance(node, list):
        items = value if isinstance(value, list) else []
        return [conform(node[0], item) for item in items if isinstance(item, dict)]
    value = value if isinstance(value, dict) else {}
    node = {k: v for k, v in node.items() if not k.startswith("_")}  # bez konfiguracji ekstrakcji
    out = {k: conform(v, value.get(k)) for k, v in node.items()}
    for k, v in node.items():  # pola wyliczane ze słownika
        if is_leaf(v) and (derive := v.get("derive")):
            src = out.get(derive["from"])
            out[k] = _dictionary(derive["dictionary"]).get(src) if src is not None else None
    return out
