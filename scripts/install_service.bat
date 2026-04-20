@echo off
setlocal

REM DeskPricer Windows Service Installer (requires NSSM)
REM Run as Administrator

set SERVICE_NAME=DeskPricer
set APP_DIR=C:\deskpricer
set PYTHON=%APP_DIR%\.venv\Scripts\python.exe
set LOG_DIR=C:\ProgramData\DeskPricer\logs

if not exist "%PYTHON%" (
    echo ERROR: Python not found at %PYTHON%
    echo Please install the app to %APP_DIR% first.
    exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

nssm install %SERVICE_NAME% "%PYTHON%" "-m uvicorn desk_pricer.main:app --host 127.0.0.1 --port 8765 --workers 1"
nssm set %SERVICE_NAME% AppDirectory %APP_DIR%
nssm set %SERVICE_NAME% AppStdout %LOG_DIR%\stdout.log
nssm set %SERVICE_NAME% AppStderr %LOG_DIR%\stderr.log
nssm set %SERVICE_NAME% Start SERVICE_AUTO_START

echo Starting service...
nssm start %SERVICE_NAME%

if %errorlevel% neq 0 (
    echo ERROR: Failed to start service.
    exit /b 1
)

echo DeskPricer service installed and started.
endlocal
