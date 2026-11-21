@echo off
REM Odwolania2json: PDF-y z input\ -> pliki JSON w output\ (ta sama struktura folderow i nazwy).
REM Wszystko dziala lokalnie na CPU (OCR, klasyfikacja, ekstrakcja) - bez API, GPU i treningu.
REM Python nie musi byc zainstalowany - tools\setup.bat przygotuje go przy pierwszym uruchomieniu.
setlocal
cd /d "%~dp0"
call tools\setup.bat || goto :error

REM sciezki w argumentach (--input, --output) liczone od folderu projektu
set "PYTHONPATH=%~dp0backend"
.venv\Scripts\python -m app.cli %*
exit /b %errorlevel%

:error
pause
exit /b 1
