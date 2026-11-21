"""F1 na poziomie pól: porównuje output/ z wzorcowymi JSON-ami ze zbioru treningowego UZP.

Użycie (z katalogu głównego):
  python backend/scripts/evaluate.py --gold data/hacknation-2026/dane --pred output/dane

Dla każdego PDF w --gold oczekiwany JSON to plik o tej samej nazwie; w danych UZP
potwierdzenie_przelewu.pdf ma wzorzec przelew.json. PDF bez wzorca = dokument negatywny
(oczekiwany pusty JSON).
"""

import argparse
import json
from collections import Counter
from pathlib import Path

GOLD_ALIASES = {"potwierdzenie_przelewu": "przelew"}


def flatten(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from flatten(v, f"{prefix}{k}.")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from flatten(v, f"{prefix}{i}.")
    elif obj is not None:
        v = float(obj) if isinstance(obj, (int, float)) and not isinstance(obj, bool) else str(obj).strip()
        yield prefix.rstrip("."), v


def load(path: Path):
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def gold_path(pdf: Path) -> Path:
    p = pdf.with_suffix(".json")
    return p if p.exists() else pdf.with_name(GOLD_ALIASES.get(pdf.stem, pdf.stem) + ".json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--errors", action="store_true", help="wypisz różnice")
    a = ap.parse_args()

    tp = fp = fn = 0
    per_field = Counter()
    for pdf in sorted(a.gold.rglob("*.pdf")):
        rel = pdf.relative_to(a.gold)
        gold = set(flatten(load(gold_path(pdf))))
        pred = set(flatten(load(a.pred / rel.with_suffix(".json"))))
        tp += len(gold & pred)
        fp += len(pred - gold)
        fn += len(gold - pred)
        for path, _ in gold - pred:
            per_field[f"{pdf.stem}:{path}"] += 1
        if a.errors and gold != pred:
            print(f"\n{rel}\n  brak/źle: {sorted(gold - pred)}\n  nadmiar:  {sorted(pred - gold)}")

    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    print(f"\nprecision={p:.3f} recall={r:.3f} F1={f1:.3f}  (TP={tp} FP={fp} FN={fn})")
    print("\nNajczęściej błędne pola:")
    for k, n in per_field.most_common(15):
        print(f"  {n:4}  {k}")


if __name__ == "__main__":
    main()
