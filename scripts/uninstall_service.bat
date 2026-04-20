@echo off
setlocal

REM DeskPricer Windows Service Uninstaller
REM Run as Administrator

set SERVICE_NAME=DeskPricer

echo Stopping service...
nssm stop %SERVICE_NAME%

echo Removing service...
nssm remove %SERVICE_NAME% confirm

echo Done.
endlocal
