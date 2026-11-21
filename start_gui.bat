@echo off
REM Odwolania2json - GUI w przegladarce: http://localhost:8000
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    py -3.13 -m venv .venv || python -m venv .venv || goto :error
    .venv\Scripts\python -m pip install -q -r requirements.txt || goto :error
)

cd backend
start "" http://localhost:8000
..\.venv\Scripts\python -m uvicorn app.main:app --port 8000
exit /b %errorlevel%

:error
pause
exit /b 1
