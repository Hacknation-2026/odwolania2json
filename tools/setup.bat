@echo off
REM Przygotowuje srodowisko .venv (Python 3.13 + zaleznosci z requirements.txt).
REM Nie wymaga wczesniej zainstalowanego Pythona ani uprawnien administratora; GPU niepotrzebne.
REM   1. jest juz .venv                -> tylko doinstalowanie zmienionych zaleznosci
REM   2. jest Python 3.13 w systemie   -> .venv z niego
REM   3. brak Pythona 3.13             -> pobiera uv (https://github.com/astral-sh/uv, MIT/Apache-2.0),
REM                                       ktory instaluje Pythona 3.13 w tools\python (wewnatrz projektu)
REM Pierwsze uruchomienie potrzebuje internetu i trwa kilka minut; kolejne - kilka sekund.
REM Wywolywany przez start.bat, start_gui.bat i train.bat (call tools\setup.bat).
setlocal
cd /d "%~dp0.."
set "VENV_PY=.venv\Scripts\python.exe"
set "UV=%CD%\tools\uv\uv.exe"
set "UV_PYTHON_INSTALL_DIR=%CD%\tools\python"

if exist "%VENV_PY%" goto :deps

if defined ODW_FORCE_UV goto :with_uv
py -3.13 -c "import sys" >nul 2>&1
if errorlevel 1 goto :with_uv
echo [setup] Tworze .venv z zainstalowanego Pythona 3.13...
py -3.13 -m venv .venv
if errorlevel 1 goto :with_uv
goto :deps

:with_uv
call :get_uv || exit /b 1
echo [setup] Instaluje Pythona 3.13 do tools\python i tworze .venv ...
"%UV%" venv --python 3.13 --python-preference only-managed .venv
if errorlevel 1 (
    echo [setup] BLAD: nie udalo sie utworzyc srodowiska Pythona 3.13.
    exit /b 1
)

:deps
REM zaleznosci instalowane tylko przy pierwszym uruchomieniu i po zmianie requirements.txt
fc /b requirements.txt .venv\requirements.installed >nul 2>&1
if not errorlevel 1 exit /b 0
echo [setup] Instaluje zaleznosci (pierwszy raz: kilka minut, potrzebny internet)...
if exist "%UV%" (
    "%UV%" pip install --python "%VENV_PY%" -r requirements.txt
) else (
    "%VENV_PY%" -m pip install --disable-pip-version-check -q -r requirements.txt
)
if errorlevel 1 (
    echo [setup] BLAD: instalacja zaleznosci nie powiodla sie - sprawdz polaczenie z internetem.
    exit /b 1
)
copy /y requirements.txt .venv\requirements.installed >nul
exit /b 0

:get_uv
if exist "%UV%" exit /b 0
echo [setup] Brak Pythona 3.13 - pobieram uv (instalator Pythona, ok. 20 MB)...
if not exist tools\uv mkdir tools\uv
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol='Tls12';" ^
  "Invoke-WebRequest -UseBasicParsing 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' -OutFile 'tools\uv\uv.zip';" ^
  "Expand-Archive -Force 'tools\uv\uv.zip' 'tools\uv'; Remove-Item 'tools\uv\uv.zip'"
if not exist "%UV%" (
    echo [setup] BLAD: nie udalo sie pobrac uv. Zainstaluj Pythona 3.13 z https://www.python.org/downloads/
    echo         albo sprawdz polaczenie z internetem i uruchom ponownie.
    exit /b 1
)
exit /b 0
