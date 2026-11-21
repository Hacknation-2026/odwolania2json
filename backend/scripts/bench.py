"""Benchmark na danych UZP: F1 osobno dla dokumentów syntetycznych, negatywów i prawdziwych skanów.

Prawdziwe skany (dane/skany) są podzielone na stałe: część "dev" do pracy nad regułami
i odłożoną część "holdout" (pliki 0003, 0006, 0009 każdego typu), na którą nie patrzymy
przy pisaniu reguł - tylko ona uczciwie przybliża wynik na ukrytym zbiorze UZP.

Tekst stron (z OCR) jest zapisywany w data/cache/, więc kolejne uruchomienia trwają sekundy.
Cache zależy od ustawień OCR (rozdzielczość itd.) - po ich zmianie liczy się od nowa.

Użycie (z backend/):
  python scripts/bench.py                       # podsumowanie F1
  python scripts/bench.py --fields skany-dev    # błędy per pole dla wybranej części
  python scripts/bench.py --show skany/odwolania/0002/0002.pdf   # wynik vs wzorzec
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.classes.registry import load_classes  # noqa: E402
from app.config import ROOT_DIR, get_settings  # noqa: E402
from app.dataset import gold_path, load_gold  # noqa: E402
from app.extraction.pdf_text import PageText, extract_pages  # noqa: E402
from app.pipeline import process_document  # noqa: E402

DANE = ROOT_DIR / "data" / "hacknation-2026" / "dane"
CACHE = ROOT_DIR / "data" / "cache"
HOLDOUT = {"0003", "0006", "0009"}
SUBSETS = ["syntetyczne", "negatywne", "skany-dev", "skany-holdout"]


def subset(rel: str) -> str:
    if rel.startswith("skany/"):
        return "skany-holdout" if Path(rel).stem in HOLDOUT else "skany-dev"
    return "negatywne" if rel.startswith("negatywne/") or not load_gold(gold_path(DANE / rel)) else "syntetyczne"


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


def cached_loader(pdf: Path):
    """load_pages(end, start) z cache na dysku (klucz: treść PDF + ustawienia OCR)."""
    s = get_settings()
    data = pdf.read_bytes()
    key = hashlib.sha1(data).hexdigest()
    path = CACHE / f"ocr-dpi{s.ocr_dpi}-min{s.ocr_min_chars}-b{s.ocr_rec_batch}" / f"{key}.json"
    pages = [PageText(**p) for p in json.loads(path.read_text(encoding="utf-8"))] if path.exists() else []

    def load(end: int, start: int = 0) -> list[PageText]:
        nonlocal pages
        if len(pages) < end and not (pages and pages[-1].source == "end"):
            more = extract_pages(data, end, start=len(pages))
            pages += more
            if len(pages) < end:  # dokument krótszy niż end - zapamiętaj, żeby nie pytać ponownie
                pages.append(PageText(len(pages) + 1, "", "end"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps([p.__dict__ for p in pages], ensure_ascii=False), encoding="utf-8")
        return [p for p in pages[start:end] if p.source != "end"]

    return load


def run() -> dict[str, dict]:
    results = {}
    for pdf in sorted(DANE.rglob("*.pdf")):
        rel = pdf.relative_to(DANE).as_posix()
        started = time.perf_counter()
        r = process_document(cached_loader(pdf), pdf.name)
        results[rel] = {"pred": r["data"] or {}, "type": r["document_type"], "seconds": time.perf_counter() - started}
    return results


def score(results: dict, rels: list[str]) -> tuple[float, float, float, list]:
    tp = fp = fn = 0
    errors = []
    for rel in rels:
        gold = set(flatten(load_gold(gold_path(DANE / rel))))
        pred = set(flatten(results[rel]["pred"]))
        tp += len(gold & pred)
        fp += len(pred - gold)
        fn += len(gold - pred)
        g, p = dict(gold), dict(pred)
        for k in set(g) | set(p):
            if g.get(k) != p.get(k):
                errors.append((rel, k, g.get(k), p.get(k)))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return prec, rec, 2 * prec * rec / (prec + rec) if prec + rec else 0.0, errors


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fields", choices=SUBSETS, help="błędy per pole dla tej części")
    ap.add_argument("--show", help="ścieżka PDF względem dane/: wynik i wzorzec obok siebie")
    ap.add_argument("--save", type=Path, help="zapisz wyniki (JSON) do porównań")
    args = ap.parse_args()

    load_classes()
    results = run()
    groups = defaultdict(list)
    for rel in results:
        groups[subset(rel)].append(rel)

    print(f"{'część':15} {'pliki':>5} {'P':>6} {'R':>6} {'F1':>6}")
    for name in SUBSETS:
        if name == "negatywne":  # brak pól - liczy się tylko, czy dokument został odrzucony
            wrong = [rel for rel in groups[name] if results[rel]["pred"]]
            print(f"{name:15} {len(groups[name]):5}  odrzucone poprawnie: {len(groups[name]) - len(wrong)}"
                  + (f" (błędnie rozpoznane: {', '.join(wrong)})" if wrong else ""))
            continue
        p, r, f1, _ = score(results, groups[name])
        print(f"{name:15} {len(groups[name]):5} {p:6.3f} {r:6.3f} {f1:6.3f}")
    all_rels = [rel for name in SUBSETS for rel in groups[name]]
    p, r, f1, _ = score(results, all_rels)
    print(f"{'razem':15} {len(all_rels):5} {p:6.3f} {r:6.3f} {f1:6.3f}")

    if args.fields:
        _, _, _, errors = score(results, groups[args.fields])
        by_field = defaultdict(lambda: [0, 0, 0])  # [brak, zła wartość, nadmiarowe]
        for rel, key, g, pv in errors:
            field = re.sub(r"\.\d+\.", ".N.", f"{Path(rel).parts[-3] if rel.startswith('skany') else Path(rel).stem}:{key}")
            by_field[field][0 if pv is None else 2 if g is None else 1] += 1
        print(f"\n{'pole':60} {'brak':>5} {'źle':>5} {'nadm.':>5}")
        for field, (miss, wrong, extra) in sorted(by_field.items(), key=lambda kv: -sum(kv[1])):
            print(f"{field:60} {miss:5} {wrong:5} {extra:5}")

    if args.show:
        gold = dict(flatten(load_gold(gold_path(DANE / args.show))))
        pred = dict(flatten(results[args.show]["pred"]))
        for k in sorted(set(gold) | set(pred)):
            mark = "  " if gold.get(k) == pred.get(k) else "XX"
            print(f"{mark} {k:45} wzorzec={gold.get(k)!r}  wynik={pred.get(k)!r}")

    if args.save:
        args.save.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
