@echo off
REM Odwolania2json - GUI w przegladarce (adres wypisany ponizej, domyslnie http://localhost:8765)
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo Tworze srodowisko Python 3.13...
    py -3.13 -m venv .venv || python -m venv .venv || goto :error
    .venv\Scripts\python -m pip install -q -r requirements.txt || goto :error
)

if not exist .env (
    echo Brak pliku .env - skopiuj .env.example do .env i uzupelnij LLM_API_KEY
    goto :error
)

cd backend
..\.venv\Scripts\python -m app.gui || goto :error
exit /b 0

:error
echo.
echo Wystapil blad - szczegoly powyzej.
pause
exit /b 1
