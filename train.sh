#!/usr/bin/env bash
# Trenuje lokalny klasyfikator typu dokumentu -> model/document_classifier.joblib
# Przyklady: data/hacknation-2026/dane (uklad UZP) oraz training/<klasa>/*.pdf, training/brak/*.pdf
# Sciezki w argumentach (--data) liczone od folderu projektu.
set -euo pipefail
cd "$(dirname "$0")"
bash tools/setup.sh  # bash: dziala tez bez praw wykonywania (np. po rozpakowaniu ZIP)
export PYTHONPATH="$PWD/backend${PYTHONPATH:+:$PYTHONPATH}"
exec .venv/bin/python -m app.train_classifier "$@"
