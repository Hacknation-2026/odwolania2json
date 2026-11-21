"""Training/evaluation data layout.

Two ways to give examples (both can live in the same folder tree):
  1. UZP layout: <case>/<doc>.pdf next to its expected JSON <doc>.json. An empty JSON means
     a document outside the classes; otherwise the class is the one whose `output` template in
     config/classes has the same top-level keys as the JSON. A PDF without a JSON in a folder
     that has other JSONs is a negative too.
  2. Folder per class: <dir>/<class name>/*.pdf, and <dir>/brak/*.pdf for other documents.
"""

from __future__ import annotations

import json
from pathlib import Path

# UZP data quirk: potwierdzenie_przelewu.pdf has its expected JSON in przelew.json
GOLD_ALIASES = {"potwierdzenie_przelewu": "przelew"}
NEGATIVE_DIRS = {"brak", "negatywne", "inne"}


def gold_path(pdf: Path) -> Path:
    p = pdf.with_suffix(".json")
    return p if p.exists() else pdf.with_name(GOLD_ALIASES.get(pdf.stem, pdf.stem) + ".json")


def load_gold(path: Path) -> dict:
    text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    return json.loads(text) if text else {}


def label_for(pdf: Path, root: Path, classes: dict) -> str | None:
    """Class name, "" for a negative example, or None when the PDF has no label."""
    gold = gold_path(pdf)
    if gold.exists():
        data = load_gold(gold)
        if not data:
            return ""
        for name, doc_class in classes.items():
            if set(doc_class.output) == set(data):
                return name
        return None
    if any(pdf.parent.glob("*.json")):  # UZP case folder: a PDF without its JSON is a negative
        return ""
    for part in pdf.relative_to(root).parts[:-1]:
        if part in classes:
            return part
        if part.lower() in NEGATIVE_DIRS:
            return ""
    return None
