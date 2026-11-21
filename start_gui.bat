@echo off
REM Odwolania2json - GUI w przegladarce (adres wypisany ponizej, domyslnie http://localhost:8765)
REM Wszystko dziala lokalnie - bez API, GPU i treningu. Python nie musi byc zainstalowany.
setlocal
cd /d "%~dp0"
call tools\setup.bat || goto :error

cd backend
..\.venv\Scripts\python -m app.gui || goto :error
exit /b 0

:error
echo.
echo Wystapil blad - szczegoly powyzej.
pause
exit /b 1
