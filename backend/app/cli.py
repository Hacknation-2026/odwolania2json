"""CLI: input/<sprawa>/*.pdf -> output/<sprawa>/<nazwa>.json (wymóg UZP). Wszystko lokalnie.

Każde uruchomienie zaczyna od wyczyszczenia wyników z poprzednich uruchomień w output/,
więc po przebiegu output/ odpowiada dokładnie PDF-om z input/. input/ nie jest zmieniany.
Dla dokumentów spoza klas i nieczytelnych PDF-ów zapisywany jest pusty plik .json.
Ślad przetwarzania (klasyfikacja, źródło tekstu, wynik ekstrakcji) trafia do logs/.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from app.config import get_settings
from app.pipeline import process_pdf


def remove_empty_dirs(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def clear_previous_outputs(output_dir: Path) -> int:
    """Usuwa pliki .json z poprzednich uruchomień (i puste po nich foldery)."""
    if not output_dir.is_dir():
        return 0
    removed = 0
    for path in output_dir.rglob("*.json"):
        path.unlink()
        removed += 1
    remove_empty_dirs(output_dir)
    return removed


def run(input_dir: Path, output_dir: Path, trace_dir: Path | None) -> int:
    pdfs = sorted(p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    if not pdfs:
        print(f"Brak plików PDF w {input_dir}")
        return 0
    errors = 0
    started = time.perf_counter()
    for i, pdf in enumerate(pdfs, 1):
        rel = pdf.relative_to(input_dir)
        out = output_dir / rel.with_suffix(".json")
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = process_pdf(pdf.read_bytes(), pdf.name)
        except Exception as e:  # jeden zły plik nie zatrzymuje całej partii
            errors += 1
            out.write_text("", encoding="utf-8")
            print(f"[{i}/{len(pdfs)}] {rel} - BŁĄD: {e}", file=sys.stderr)
            continue
        data = result["data"]
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) if data else "", encoding="utf-8")
        if trace_dir:
            trace = trace_dir / rel.with_suffix(".trace.json")
            trace.parent.mkdir(parents=True, exist_ok=True)
            trace.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        cls = result["trace"]["classification"]
        print(f"[{i}/{len(pdfs)}] {rel} -> {result['document_type']} "
              f"({cls['confidence']:.2f}, {result['trace']['seconds']}s)")
    print(f"Gotowe: {len(pdfs)} plików w {time.perf_counter() - started:.0f}s, wyniki w {output_dir}")
    return errors


def main() -> None:
    s = get_settings()
    ap = argparse.ArgumentParser(description="Odwołania2json - PDF -> JSON (lokalnie, bez API)")
    ap.add_argument("--input", type=Path, default=s.input_dir)
    ap.add_argument("--output", type=Path, default=s.output_dir)
    ap.add_argument("--trace", type=Path, default=s.trace_dir, help="folder śladów przetwarzania")
    ap.add_argument("--no-trace", action="store_true")
    ap.add_argument("--keep-output", action="store_true",
                    help="nie usuwaj wyników poprzednich uruchomień z domyślnego output/")
    a = ap.parse_args()
    # czyścimy tylko domyślny output/ aplikacji; folder podany w --output nie jest czyszczony
    if not a.keep_output and a.output.resolve() == s.output_dir.resolve():
        clear_previous_outputs(a.output)
    errors = run(a.input, a.output, None if a.no_trace else a.trace)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
