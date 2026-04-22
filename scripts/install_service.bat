@echo off
setlocal

REM DeskPricer Windows Service Installer (requires NSSM)
REM Run as Administrator

set SERVICE_NAME=DeskPricer

REM Derive APP_DIR from the location of this batch file (scripts\install_service.bat)
set APP_DIR=%~dp0..
set PYTHON=%APP_DIR%\.venv\Scripts\python.exe
set LOG_DIR=C:\ProgramData\DeskPricer\logs

if not exist "%PYTHON%" (
    echo ERROR: Python not found at %PYTHON%
    echo Please install the app and its virtual environment first.
    exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Use the package entry point so port/env logic in main.py is respected
nssm install %SERVICE_NAME% "%PYTHON%" "-m deskpricer.main"
nssm set %SERVICE_NAME% AppDirectory "%APP_DIR%"
nssm set %SERVICE_NAME% AppStdout "%LOG_DIR%\stdout.log"
nssm set %SERVICE_NAME% AppStderr "%LOG_DIR%\stderr.log"
nssm set %SERVICE_NAME% Start SERVICE_AUTO_START

echo Starting service...
nssm start %SERVICE_NAME%

if %errorlevel% neq 0 (
    echo ERROR: Failed to start service.
    exit /b 1
)

echo DeskPricer service installed and started.
endlocal
