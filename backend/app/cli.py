"""CLI: przetwarza input/<sprawa>/*.pdf -> output/<sprawa>/<nazwa>.json.

Dla dokumentów spoza klas zapisywany jest pusty plik .json (wymóg UZP).
Ślad przetwarzania (klasyfikacja, źródło tekstu, surowa odpowiedź LLM) trafia do logs/.
"""

import argparse
import json
import sys
from pathlib import Path

from app.config import get_settings
from app.pipeline import process_pdf


def run(input_dir: Path, output_dir: Path, trace_dir: Path | None, overwrite: bool) -> int:
    pdfs = sorted(p for p in input_dir.rglob("*") if p.suffix.lower() == ".pdf")
    if not pdfs:
        print(f"Brak plików PDF w {input_dir}")
        return 0
    errors = 0
    for i, pdf in enumerate(pdfs, 1):
        rel = pdf.relative_to(input_dir)
        out = output_dir / rel.with_suffix(".json")
        if out.exists() and not overwrite:
            print(f"[{i}/{len(pdfs)}] {rel} - pominięto (już istnieje)")
            continue
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
        print(f"[{i}/{len(pdfs)}] {rel} -> {result['document_type']} ({cls['confidence']:.2f})")
    return errors


def main() -> None:
    s = get_settings()
    ap = argparse.ArgumentParser(description="Odwołania2json - PDF -> JSON")
    ap.add_argument("--input", type=Path, default=s.input_dir)
    ap.add_argument("--output", type=Path, default=s.output_dir)
    ap.add_argument("--trace", type=Path, default=s.trace_dir, help="folder śladów przetwarzania")
    ap.add_argument("--no-trace", action="store_true")
    ap.add_argument("--overwrite", action="store_true", help="nadpisz istniejące wyniki")
    a = ap.parse_args()
    if not s.llm_api_key:
        sys.exit("Brak LLM_API_KEY - uzupełnij plik .env")
    errors = run(a.input, a.output, None if a.no_trace else a.trace, a.overwrite)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
