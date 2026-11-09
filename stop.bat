@echo off
setlocal enabledelayedexpansion

title Stop TideTrace
cd /d "%~dp0"

set "PORT=8000"
set "PID_FILE=%~dp0data\tidetrace-server.pid"

echo ===================================================
echo               Stopping TideTrace
echo ===================================================

rem 1. Terminate PID from PID file if it exists
if exist "%PID_FILE%" (
    set /p SERVER_PID=<"%PID_FILE%"
    if defined SERVER_PID (
        echo [INFO] Stopping server process PID !SERVER_PID!...
        powershell -NoProfile -Command "Stop-Process -Id !SERVER_PID! -Force -ErrorAction SilentlyContinue" >nul 2>&1
    )
    del /f /q "%PID_FILE%" >nul 2>&1
)

rem 2. Terminate any process still listening on port 8000
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo [OK] TideTrace server stopped. Port %PORT% is clear.
exit /b 0
