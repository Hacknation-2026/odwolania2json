#!/usr/bin/env bash
# Odwolania2json: PDF-y z input/ -> pliki JSON w output/ (ta sama struktura folderow i nazwy).
# Wszystko dziala lokalnie na CPU (OCR, klasyfikacja, ekstrakcja) - bez API, GPU i treningu.
# Python nie musi byc zainstalowany - tools/setup.sh przygotuje go przy pierwszym uruchomieniu.
# Sciezki w argumentach (--input, --output) liczone od folderu projektu.
set -euo pipefail
cd "$(dirname "$0")"
bash tools/setup.sh  # bash: dziala tez bez praw wykonywania (np. po rozpakowaniu ZIP)
export PYTHONPATH="$PWD/backend${PYTHONPATH:+:$PYTHONPATH}"
exec .venv/bin/python -m app.cli "$@"
