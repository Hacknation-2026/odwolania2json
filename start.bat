@echo off
REM Odwolania2json: PDF-y z input\ -> pliki JSON w output\ (ta sama struktura folderow i nazwy).
REM Wszystko dziala lokalnie (OCR, klasyfikacja, ekstrakcja) - bez API i bez treningu.
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo Tworze srodowisko Python 3.13...
    py -3.13 -m venv .venv || python -m venv .venv || goto :error
)
REM szybkie, gdy wszystko jest juz zainstalowane
.venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt || goto :error

cd backend
..\.venv\Scripts\python -m app.cli %*
exit /b %errorlevel%

:error
pause
exit /b 1
