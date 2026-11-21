import json
import re
from pathlib import Path

import pytest

from app.classes.registry import load_classes
from app.normalizers import bzp, krs, ted, to_date, to_number
from app.schema import conform, to_json_schema

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "data" / "hacknation-2026" / "dane"
CLASS_FOR_GOLD = {"odwolanie": "odwolanie", "pelnomocnictwo": "pelnomocnictwo", "przelew": "przelew"}


def test_classes_load():
    classes = load_classes()
    assert {"odwolanie", "pelnomocnictwo", "przelew"} <= classes.keys()
    for c in classes.values():
        schema = to_json_schema(c.output)
        assert schema["type"] == "object"


def _shape(obj):
    if isinstance(obj, dict):
        return {k: _shape(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_shape(obj[0])] if obj else []
    return None


@pytest.mark.skipif(not GOLD.exists(), reason="brak danych UZP w data/hacknation-2026")
@pytest.mark.parametrize("gold_name", CLASS_FOR_GOLD)
def test_template_matches_gold_and_conform_is_identity(gold_name):
    """Szablon z YAML ma te same klucze co wzorce UZP, a conform() nie psuje poprawnych danych."""
    doc_class = load_classes()[CLASS_FOR_GOLD[gold_name]]
    for path in sorted(GOLD.glob(f"*/{gold_name}.json")):
        gold = json.loads(path.read_text(encoding="utf-8"))
        result = conform(doc_class.output, gold)
        assert _shape(result) == _shape(gold) or not gold, path
        assert result == gold, path


def test_normalizers():
    assert ted("2026/S086-999073") == "999073-2026"
    assert ted("2025/S 123-363730") == "363730-2025"
    assert bzp("2026/BZP 00999778") == "2026/BZP00999778"
    assert krs("244633") == "0000244633"
    assert to_date("Gdańsk, dnia 3 września 2026 roku") == "2026-09-03"
    assert to_date("13.10.2025") == "2025-10-13"
    assert to_number("10 000,00 zł") == 10000.0
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", to_date("2025-1-5"))
