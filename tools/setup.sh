#!/usr/bin/env bash
# Przygotowuje srodowisko .venv (Python 3.12 + zaleznosci z requirements.txt) - Linux (Ubuntu).
# Nie wymaga wczesniej zainstalowanego Pythona 3.12 ani uprawnien administratora; GPU niepotrzebne.
#   1. jest juz .venv                -> tylko doinstalowanie zmienionych zaleznosci
#   2. jest Python 3.12+ w systemie  -> .venv z niego (jesli dziala modul venv)
#   3. brak Pythona 3.12             -> pobiera uv (https://github.com/astral-sh/uv, MIT/Apache-2.0),
#                                       ktory instaluje Pythona 3.12 w tools/python (wewnatrz projektu)
# Pierwsze uruchomienie potrzebuje internetu i trwa kilka minut; kolejne - ulamek sekundy.
# Wywolywany przez start.sh, start_gui.sh i train.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
VENV_PY="$ROOT/.venv/bin/python"
UV="$ROOT/tools/uv/uv"
export UV_PYTHON_INSTALL_DIR="$ROOT/tools/python"

log() { echo "[setup] $*"; }

find_python() {
    for candidate in python3.12 python3; do
        if command -v "$candidate" >/dev/null 2>&1 &&
            "$candidate" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)' 2>/dev/null; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

download() {  # download <url> <file>: curl, wget albo Python, co jest w systemie
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$1" -o "$2"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$2" "$1"
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' "$1" "$2"
    else
        return 1
    fi
}

get_uv() {
    [ -x "$UV" ] && return 0
    case "$(uname -m)" in
        x86_64 | amd64) target="x86_64-unknown-linux-gnu" ;;
        aarch64 | arm64) target="aarch64-unknown-linux-gnu" ;;
        *) log "BLAD: nieobslugiwana architektura $(uname -m) - zainstaluj Pythona 3.12 recznie."; return 1 ;;
    esac
    log "Brak Pythona 3.12 - pobieram uv (instalator Pythona, ok. 20 MB)..."
    mkdir -p "$ROOT/tools/uv"
    if ! download "https://github.com/astral-sh/uv/releases/latest/download/uv-$target.tar.gz" "$ROOT/tools/uv/uv.tar.gz"; then
        log "BLAD: nie udalo sie pobrac uv. Sprawdz polaczenie z internetem albo zainstaluj Pythona 3.12"
        log "       (np. sudo apt install python3.12 python3.12-venv) i uruchom ponownie."
        return 1
    fi
    tar -xzf "$ROOT/tools/uv/uv.tar.gz" -C "$ROOT/tools/uv" --strip-components=1
    rm -f "$ROOT/tools/uv/uv.tar.gz"
    [ -x "$UV" ]
}

if [ -x "$VENV_PY" ]; then
    if ! "$VENV_PY" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)' 2>/dev/null; then
        log "Istniejace .venv ma inna wersje Pythona ($("$VENV_PY" --version 2>/dev/null || echo 'nieznana')). Tworze na nowo dla 3.12..."
        rm -rf .venv
    fi
fi

if [ ! -x "$VENV_PY" ]; then
    if [ -z "${ODW_FORCE_UV:-}" ] && PY="$(find_python)" && log "Tworze .venv z $($PY --version)..." && "$PY" -m venv .venv 2>/dev/null; then
        :
    else
        rm -rf .venv  # np. brak pakietu python3.x-venv - wtedy uv
        get_uv
        log "Instaluje Pythona 3.12 do tools/python i tworze .venv ..."
        "$UV" venv --python 3.12 --python-preference only-managed .venv
    fi
fi

# zaleznosci instalowane tylko przy pierwszym uruchomieniu i po zmianie requirements.txt
if cmp -s requirements.txt .venv/requirements.installed; then
    exit 0
fi
log "Instaluje zaleznosci (pierwszy raz: kilka minut, potrzebny internet)..."
if [ -x "$UV" ]; then
    "$UV" pip install --python "$VENV_PY" -r requirements.txt
else
    "$VENV_PY" -m pip install --disable-pip-version-check -q -r requirements.txt
fi
cp requirements.txt .venv/requirements.installed
