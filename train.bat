@echo off
REM Trenuje lokalny klasyfikator typu dokumentu -> model\document_classifier.joblib
REM Przyklady: data\hacknation-2026\dane (uklad UZP) oraz training\<klasa>\*.pdf, training\brak\*.pdf
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo Tworze srodowisko Python 3.13...
    py -3.13 -m venv .venv || python -m venv .venv || goto :error
    .venv\Scripts\python -m pip install -q -r requirements.txt || goto :error
)

cd backend
..\.venv\Scripts\python -m app.train_classifier %* || goto :error
pause
exit /b 0

:error
pause
exit /b 1
