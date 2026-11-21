"""Train the local document-type model from example PDFs (see app/dataset.py for the layout).

Usage (from backend/):  python -m app.train_classifier [--data DIR ...] [--no-eval]

Classes come from config/classes/*.yaml, so a new document type = YAML file + a few example
PDFs + this command. Before saving, the model is cross-validated with whole cases held out.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter
from pathlib import Path

import joblib
from sklearn.model_selection import GroupKFold

from app.classes.registry import load_classes
from app.classifier import classifier_text
from app.config import get_settings
from app.dataset import label_for
from app.extraction.pdf_text import extract_pages
from app.text_model import NEGATIVE_LABEL, TextModel

NEGATIVE_PAGES = 12  # every page of a negative document is a separate "other document" example
MIN_NEGATIVE_CHARS = 200


def collect(dirs: list[Path]) -> tuple[list[str], list[str], list[str], list[str]]:
    """Returns texts, labels, ids and cross-validation groups."""
    classes = load_classes()
    s = get_settings()
    texts, labels, ids, groups = [], [], [], []
    seen: set[str] = set()
    for root in dirs:
        if not root.is_dir():
            continue
        for pdf in sorted(root.rglob("*.pdf")):
            label = label_for(pdf, root, classes)
            if label is None:
                print(f"  pominięto (brak etykiety): {pdf}")
                continue
            data = pdf.read_bytes()
            digest = hashlib.sha1(data).hexdigest()
            if digest in seen:  # UZP data repeats some negatives across cases
                continue
            seen.add(digest)
            doc_id = pdf.relative_to(root).as_posix()
            if label:
                pages = extract_pages(data, s.classify_max_pages)
                text = classifier_text(pages)
                if text.strip():
                    texts.append(text)
                    labels.append(label)
                    ids.append(doc_id)
                    groups.append(str(pdf.parent))  # documents of one case stay together
                continue
            for page in extract_pages(data, NEGATIVE_PAGES):
                if len(page.text) >= MIN_NEGATIVE_CHARS:
                    texts.append(page.text)
                    labels.append(NEGATIVE_LABEL)
                    ids.append(f"{doc_id}#s{page.number}")
                    groups.append(digest)  # all pages of one negative document stay together
    return texts, labels, ids, groups


def cross_validate(texts, labels, ids, groups, folds: int = 5) -> None:
    min_confidence = get_settings().min_confidence
    errors, total = [], 0
    for train_idx, test_idx in GroupKFold(n_splits=folds).split(texts, labels, groups):
        model = TextModel.fit([texts[i] for i in train_idx], [labels[i] for i in train_idx])
        for i in test_idx:
            p = model.predict(texts[i], min_confidence)
            got = p.label or NEGATIVE_LABEL
            total += 1
            if got != labels[i]:
                errors.append(f"  {ids[i]}: oczekiwano {labels[i]}, wynik {got} (pewność {p.confidence:.2f})")
    print(f"Walidacja krzyżowa ({folds} części, całe sprawy odłożone): "
          f"{total - len(errors)}/{total} poprawnie ({(total - len(errors)) / total:.1%})")
    print("\n".join(errors) if errors else "  bez błędów")


def main() -> None:
    s = get_settings()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, nargs="+", default=s.training_data_dirs, help="foldery z przykładami")
    ap.add_argument("--model", type=Path, default=s.classifier_model_path)
    ap.add_argument("--no-eval", action="store_true", help="bez walidacji krzyżowej")
    args = ap.parse_args()

    print(f"Klasy z YAML: {', '.join(load_classes())}")
    texts, labels, ids, groups = collect(args.data)
    counts = Counter(labels)
    print("Przykłady: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    missing = [c for c in load_classes() if c not in counts]
    if missing:
        print(f"UWAGA: brak przykładów dla klas {missing} - model ich nie rozpozna.")
    if NEGATIVE_LABEL not in counts:
        sys.exit("Brak przykładów dokumentów spoza klas (np. folder brak/) - model nie nauczy się ich odrzucać.")
    if not args.no_eval and len(set(groups)) >= 5:
        cross_validate(texts, labels, ids, groups)

    model = TextModel.fit(texts, labels, ids)
    args.model.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model.to_artifact(), args.model, compress=3)
    print(f"Zapisano model: {args.model} ({args.model.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
