"""Generic, YAML-driven field extraction - a new document class needs no Python code.

Any leaf of a class `output` template may carry an `extract:` spec; object nodes may limit the
text their fields see with `_section`, and list items may split the text into blocks with
`_split`. Labels, keywords and patterns are matched case-insensitively and without Polish
diacritics (OCR often loses them); values are taken from the original text.

Leaf spec (all keys optional except one of after / pattern / keywords / value: flag):

  extract:
    after: ["Numer ogłoszenia", "Ogłoszenie nr"]  # labels (regex); value follows the first one found
    value: line          # line | text | date | amount | account | digits | email | person | word | flag
    pattern: "..."       # regex with one group, searched after the label (or in the whole text)
    until: ["Data", "Kwota"]   # value: text - stop at a line starting with one of these labels
    lines: 3             # value: text - at most this many lines (default 5)
    length: 10           # value: digits - required number of digits (or [9, 14])
    keywords:            # first entry whose pattern matches wins -> its id
      - {id: 1, pattern: "odrzuc\\w*\\s+ofert"}
    default: 0           # value when nothing is found (e.g. 0 for flags)

Object node:  _section: {from: ["Zamawiający:"], to: ["Dotyczy:", "ODWOŁANIE"]}
List item:    _split: "(?m)^\\s*\\d+\\)"      # one item per block starting with this pattern
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.schema import is_leaf

DATE = re.compile(
    r"\d{4}-\d{2}-\d{2}|\d{1,2}[.\-/ ]\d{1,2}[.\-/ ]\d{4}|"
    r"\d{1,2}\s+(?:stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|wrzesnia|"
    r"października|pazdziernika|listopada|grudnia)\s+\d{4}",
    re.I,
)
AMOUNT = re.compile(r"(?<![\w.,])-?\s?(\d{1,3}(?:[  .]?\d{3})*(?:[.,]\d{1,2})?)(?![\w])")
ACCOUNT = re.compile(r"(?:PL\s*)?\d(?:[\s-]*\d){25}", re.I)
EMAIL = re.compile(r"[\w.%+-]+@[\w.-]+\.[a-z]{2,}", re.I)


def _fold_char(ch: str) -> str:
    if ch in "łŁ":
        return "l" if ch == "ł" else "L"
    return unicodedata.normalize("NFKD", ch)[0]  # "ą" -> "a"; always one character


def fold(text: str) -> str:
    """Same length as `text` (offsets stay valid), Polish letters without diacritics."""
    return "".join(_fold_char(c) for c in text)


def _search(patterns: list[str] | str, text: str, start: int = 0) -> re.Match | None:
    """First (leftmost) match of any pattern, diacritic- and case-insensitive."""
    folded = fold(text)
    best = None
    for pattern in [patterns] if isinstance(patterns, str) else patterns:
        match = re.compile(fold(pattern), re.I | re.M).search(folded, start)
        if match and (best is None or match.start() < best.start()):
            best = match
    return best


def section(text: str, spec: dict | None) -> str:
    if not spec:
        return text
    start = _search(spec["from"], text) if spec.get("from") else None
    if spec.get("from") and not start:
        return ""
    begin = start.end() if start else 0
    end = _search(spec["to"], text, begin) if spec.get("to") else None
    return text[begin : end.start() if end else len(text)]


def split(text: str, pattern: str) -> list[str]:
    starts = [m.start() for m in re.finditer(fold(pattern), fold(text), re.I | re.M)]
    if not starts:
        return [text] if text.strip() else []
    return [text[a:b] for a, b in zip(starts, [*starts[1:], len(text)])]


def match_keywords(keywords: list[dict], text: str) -> Any:
    for entry in keywords:
        if _search(entry["pattern"], text):
            return entry["id"]
    return None


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip(" :\t"):
            return line.strip(" :\t")
    return ""


def _value(spec: dict, text: str) -> Any:
    kind = spec.get("value", "line")
    if kind == "flag":
        return 1
    if pattern := spec.get("pattern"):
        match = re.search(pattern, text, re.I | re.M)  # add (?s) in the pattern to span lines
        if not match:
            folded = re.search(fold(pattern), fold(text), re.I | re.M)
            return text[folded.start(1) : folded.end(1)].strip() if folded else None
        return match.group(1).strip()
    if kind == "line":
        return _first_line(text) or None
    if kind == "text":
        lines = []
        for line in text.splitlines():
            if not line.strip():
                if lines:
                    break
                continue
            if spec.get("until") and _search([rf"^\s*(?:{u})" for u in spec["until"]], line):
                break
            lines.append(line.strip())
            if len(lines) >= spec.get("lines", 5):
                break
        return " ".join(lines).strip(" :") or None
    if kind == "date":
        match = DATE.search(text[:200])
        return match.group() if match else None
    if kind == "amount":
        match = AMOUNT.search(text[:200])
        return match.group(1) if match else None
    if kind == "account":
        match = ACCOUNT.search(text[:300])
        return re.sub(r"\D", "", match.group())[-26:] if match else None
    if kind == "email":
        match = EMAIL.search(text[:300])
        return match.group() if match else None
    if kind == "digits":
        lengths = spec.get("length", [])
        lengths = lengths if isinstance(lengths, list) else [lengths]
        match = re.search(r"\d[\d \-]{3,25}\d|\d+", text[:120])
        if not match:
            return None
        digits = re.sub(r"\D", "", match.group())
        return digits if not lengths or len(digits) in lengths else None
    if kind == "word":
        match = re.search(r"\S+", text)
        return match.group().strip(" ,;:") if match else None
    if kind == "person":
        from app.extraction.rules import _person  # same name cleaning as the built-in rules

        for line in text.splitlines()[:3]:
            if name := _person(line):
                return name
        return None
    raise ValueError(f"Nieznany typ wartości w extract.value: {kind!r}")


def extract_leaf(spec: dict, text: str) -> Any:
    if "keywords" in spec:
        found = match_keywords(spec["keywords"], text)
        return found if found is not None else spec.get("default")
    if spec.get("after"):
        label = _search(spec["after"], text)
        found = _value(spec, text[label.end() :]) if label else None
        if label and spec.get("value") == "flag":
            found = 1
    else:
        found = _value(spec, text) if spec.get("value") != "flag" else None
    return found if found is not None else spec.get("default")


def has_rules(node: Any) -> bool:
    """True when the template contains at least one `extract:` spec."""
    if is_leaf(node):
        return "extract" in node
    if isinstance(node, list):
        return has_rules(node[0])
    return isinstance(node, dict) and any(has_rules(v) for k, v in node.items() if not k.startswith("_"))


def run(node: Any, text: str) -> Any:
    """Fills the template from `text`; fields without `extract:` stay None."""
    if is_leaf(node):
        return extract_leaf(node["extract"], text) if "extract" in node else None
    if isinstance(node, list):
        item = node[0]
        blocks = split(text, item["_split"]) if "_split" in item else [text]
        values = [run(item, block) for block in blocks]
        return [v for v in values if _any_value(v)]
    text = section(text, node.get("_section"))
    return {k: run(v, text) for k, v in node.items() if not k.startswith("_")}


def _any_value(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_any_value(v) for v in value.values())
    if isinstance(value, list):
        return any(_any_value(v) for v in value)
    return value is not None


def merge(primary: Any, fallback: Any, node: Any) -> Any:
    """Built-in result first; YAML rules fill what it left empty (or override with `override: true`)."""
    if is_leaf(node):
        if "extract" in node and node["extract"].get("override") and fallback is not None:
            return fallback
        return primary if primary is not None else fallback
    if isinstance(node, list):
        primary = primary if isinstance(primary, list) else []
        fallback = fallback if isinstance(fallback, list) else []
        if not primary:
            return fallback
        return [merge(p, fallback[i] if i < len(fallback) else None, node[0]) for i, p in enumerate(primary)]
    primary = primary if isinstance(primary, dict) else {}
    fallback = fallback if isinstance(fallback, dict) else {}
    return {k: merge(primary.get(k), fallback.get(k), v) for k, v in node.items() if not k.startswith("_")}
