"""Rejestr klas dokumentów i słowników ładowany z plików YAML w `backend/config/`.

Nowa klasa dokumentu = nowy plik w `config/classes/`, bez zmian w kodzie.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from app.config import get_settings


class DocumentClass(BaseModel):
    name: str
    label: str = ""  # display name for the GUI; falls back to `name`
    description: str
    max_pages: int = 3
    # dla skanów (strony z OCR, ~3-6 s każda na CPU) czytaj najwyżej tyle stron; None = max_pages
    max_ocr_pages: int | None = None
    instructions: str = ""
    # wbudowane reguły Pythona dla tej klasy (app/extractor.py: BUILTIN_RULES); pola z `extract:`
    # w szablonie uzupełniają ich wynik - nowa klasa może mieć wyłącznie reguły z YAML
    rules: str | None = None
    output: dict[str, Any]  # szablon wynikowego JSON-a (patrz app/schema.py)


def _load_yaml_dir(directory: Path) -> dict[str, Any]:
    return {
        p.stem: yaml.safe_load(p.read_text(encoding="utf-8"))
        for p in sorted(directory.glob("*.y*ml"))
    }


@lru_cache
def load_classes(config_dir: Path | None = None) -> dict[str, DocumentClass]:
    config_dir = config_dir or get_settings().config_dir
    classes = [DocumentClass.model_validate(d) for d in _load_yaml_dir(config_dir / "classes").values()]
    return {c.name: c for c in classes}


@lru_cache
def load_dictionaries(config_dir: Path | None = None) -> dict[str, dict[int | str, str]]:
    config_dir = config_dir or get_settings().config_dir
    return _load_yaml_dir(config_dir / "dictionaries")
