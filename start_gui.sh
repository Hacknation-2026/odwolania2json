#!/usr/bin/env bash
# Odwolania2json - GUI w przegladarce (adres wypisany ponizej, domyslnie http://localhost:8765).
# Wszystko dziala lokalnie - bez API, GPU i treningu. Python nie musi byc zainstalowany.
# Dostep z innego komputera (np. GUI z maszyny wirtualnej): GUI_HOST=0.0.0.0 ./start_gui.sh
set -euo pipefail
cd "$(dirname "$0")"
tools/setup.sh
export PYTHONPATH="$PWD/backend${PYTHONPATH:+:$PYTHONPATH}"
exec .venv/bin/python -m app.gui "$@"
