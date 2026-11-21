"""Normalizacja wartości pól. Nazwy funkcji są używane w YAML (`normalize: <nazwa>`)."""

import re
from collections.abc import Callable
from datetime import date

MONTHS = {
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5, "czerwca": 6,
    "lipca": 7, "sierpnia": 8, "września": 9, "października": 10, "listopada": 11, "grudnia": 12,
}


def digits(v: str) -> str | None:
    return re.sub(r"\D", "", v) or None


def krs(v: str) -> str | None:
    d = digits(v)
    return d.zfill(10) if d and len(d) <= 10 else d


def bzp(v: str) -> str | None:
    """'2026/BZP 00999778' -> '2026/BZP00999778'."""
    return re.sub(r"\s+", "", v).upper() or None


def ted(v: str) -> str | None:
    """'2025/S 123-363730' -> '363730-2025'; '363730-2025' bez zmian."""
    v = v.strip()
    m = re.search(r"(\d{4})\s*/\s*S\s*\d{1,3}\s*-\s*(\d{4,})", v)
    if m:
        return f"{int(m.group(2)):06d}-{m.group(1)}"
    m = re.search(r"(\d{4,})\s*-\s*(\d{4})", v)
    return f"{m.group(1)}-{m.group(2)}" if m else v or None


def to_date(v: str) -> str | None:
    """Daty polskie i ISO -> 'YYYY-MM-DD'."""
    v = v.strip().lower()
    if m := re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", v):
        y, mo, d = map(int, m.groups())
    elif m := re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", v):
        d, mo, y = map(int, m.groups())
    elif m := re.search(r"(\d{1,2})\s+([a-ząćęłńóśźż]+)\s+(\d{4})", v):
        d, y = int(m.group(1)), int(m.group(3))
        mo = MONTHS.get(m.group(2))
        if not mo:
            return None
    else:
        return None
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def to_number(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v))
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


NORMALIZERS: dict[str, Callable[[str], str | None]] = {
    "digits": digits,
    "krs": krs,
    "bzp": bzp,
    "ted": ted,
}
