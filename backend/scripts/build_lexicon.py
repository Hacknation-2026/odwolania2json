"""Builds the Polish word list used to restore diacritics lost by OCR (app/extraction/ocr_fix.py).

Source: text layers of PDFs that are NOT scans (UZP synthetic cases and negatives) plus the
values of their expected JSONs - correctly spelled Polish. Scans (dane/skany) are excluded,
so the benchmark on scans stays honest.

Usage (from backend/):  python scripts/build_lexicon.py [--data DIR ...]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import ROOT_DIR, get_settings  # noqa: E402
from app.dataset import gold_path  # noqa: E402

import pypdfium2 as pdfium  # noqa: E402

WORD = re.compile(r"[^\W\d_]{3,}")


def text_layer(pdf: Path, max_pages: int = 12) -> str:
    doc = pdfium.PdfDocument(pdf.read_bytes())
    try:
        return "\n".join(doc[i].get_textpage().get_text_range() for i in range(min(max_pages, len(doc))))
    finally:
        doc.close()


def _values(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _values(v)
    elif isinstance(obj, str):
        yield obj


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, nargs="+", default=[ROOT_DIR / "data" / "hacknation-2026" / "dane"])
    ap.add_argument("--out", type=Path, default=get_settings().config_dir / "lexicon" / "slowa.txt")
    args = ap.parse_args()

    counts: Counter[str] = Counter()
    for root in args.data:
        for pdf in sorted(root.rglob("*.pdf")):
            if "skany" in pdf.relative_to(root).parts:
                continue
            counts.update(w.lower() for w in WORD.findall(text_layer(pdf)))
            gold = gold_path(pdf)
            if gold.exists() and gold.read_text(encoding="utf-8").strip():
                for value in _values(json.loads(gold.read_text(encoding="utf-8"))):  # values, not keys
                    counts.update(w.lower() for w in WORD.findall(value))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{word}\t{n}" for word, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    args.out.write_text(
        "# słowo<TAB>liczba wystąpień - generowane przez scripts/build_lexicon.py\n" + "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    print(f"Zapisano {len(lines)} słów do {args.out}")


if __name__ == "__main__":
    main()
