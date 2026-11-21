@echo off
REM Odwolania2json: PDF-y z input\ -> pliki JSON w output\ (ta sama struktura folderow i nazwy).
REM Wszystko dziala lokalnie (klasyfikacja i ekstrakcja), bez API.
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo Tworze srodowisko Python 3.13...
    py -3.13 -m venv .venv || python -m venv .venv || goto :error
)
REM quick no-op when everything is already installed
.venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt || goto :error

.venv\Scripts\python model\src\predict.py %* || goto :error
exit /b 0

:error
pause
exit /b 1
