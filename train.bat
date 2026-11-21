@echo off
REM Trenuje lokalny klasyfikator typu dokumentu -> model\document_classifier.joblib
REM Przyklady: data\hacknation-2026\dane (uklad UZP) oraz training\<klasa>\*.pdf, training\brak\*.pdf
setlocal
cd /d "%~dp0"
call tools\setup.bat || goto :error

cd backend
..\.venv\Scripts\python -m app.train_classifier %* || goto :error
pause
exit /b 0

:error
pause
exit /b 1
