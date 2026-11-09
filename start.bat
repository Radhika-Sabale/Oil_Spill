@echo off
setlocal enabledelayedexpansion

title TideTrace Launcher
cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=8000"
set "APP_URL=http://%HOST%:%PORT%"
set "DATA_DIR=%~dp0data"
set "PID_FILE=%DATA_DIR%\tidetrace-server.pid"
set "OUT_LOG=%DATA_DIR%\server.log"
set "ERR_LOG=%DATA_DIR%\server-error.log"

if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"

echo ===================================================
echo               TideTrace Launcher
echo ===================================================

rem 1. Check if TideTrace is already running
call :check_server
if %IS_RUNNING% equ 1 (
    echo [INFO] TideTrace is already running at %APP_URL%
    echo Opening browser...
    start "" "%APP_URL%"
    exit /b 0
)

rem 2. Detect Python interpreter
set "PYTHON="
if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON=%~dp0venv\Scripts\python.exe"
) else if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv\Scripts\python.exe"
) else (
    where python >nul 2>&1
    if !errorlevel! equ 0 set "PYTHON=python"
)

if not defined PYTHON (
    echo [ERROR] Python not found!
    echo Please install Python 3.11+ or create a virtual environment in .\venv or .\.venv
    pause
    exit /b 1
)

rem 3. Support optional foreground console mode (-c or --console)
if /i "%~1"=="--console" goto FOREGROUND_MODE
if /i "%~1"=="-c" goto FOREGROUND_MODE

rem 4. Check if port is already occupied
call :check_port %PORT%
if %PORT_BUSY% equ 1 (
    echo [WARNING] Port %PORT% is currently occupied by another process.
    echo Please run stop.bat or terminate the process using port %PORT% before retrying.
    pause
    exit /b 1
)

rem 5. Launch server in background
echo [INFO] Starting TideTrace server at %HOST%:%PORT%...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$p = Start-Process -FilePath '%PYTHON%' -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '%HOST%', '--port', '%PORT%') -WorkingDirectory '%~dp0' -WindowStyle Hidden -PassThru -RedirectStandardOutput '%OUT_LOG%' -RedirectStandardError '%ERR_LOG%';" ^
    "Set-Content -LiteralPath '%PID_FILE%' -Value $p.Id"

if %errorlevel% neq 0 (
    echo [ERROR] Failed to launch server process.
    if exist "%ERR_LOG%" type "%ERR_LOG%"
    pause
    exit /b 1
)

rem Read PID
set "SERVER_PID="
if exist "%PID_FILE%" set /p SERVER_PID=<"%PID_FILE%"
if defined SERVER_PID echo [INFO] Server started with PID %SERVER_PID%.

rem 6. Wait for server to become responsive
echo [INFO] Waiting for server to initialize...
set /a ATTEMPTS=0

:WAIT_LOOP
set /a ATTEMPTS+=1

call :check_server
if %IS_RUNNING% equ 1 goto READY

rem Check if process died
if defined SERVER_PID (
    call :check_process_alive %SERVER_PID%
    if !PROC_ALIVE! equ 0 (
        echo.
        echo [ERROR] Server process PID %SERVER_PID% terminated unexpectedly!
        echo ------------------- Server Error Log -------------------
        if exist "%ERR_LOG%" type "%ERR_LOG%"
        echo --------------------------------------------------------
        if exist "%PID_FILE%" del /f /q "%PID_FILE%" >nul 2>&1
        pause
        exit /b 1
    )
)

if %ATTEMPTS% geq 25 (
    echo.
    echo [ERROR] Server startup timed out after 25 seconds.
    echo ------------------- Server Error Log -------------------
    if exist "%ERR_LOG%" type "%ERR_LOG%"
    echo --------------------------------------------------------
    pause
    exit /b 1
)

powershell -NoProfile -Command "Start-Sleep -Seconds 1" >nul 2>&1
goto WAIT_LOOP

:READY
echo [OK] TideTrace is ready!
echo [OK] Web UI available at: %APP_URL%
echo Opening browser...
start "" "%APP_URL%"
exit /b 0

:FOREGROUND_MODE
echo [INFO] Starting TideTrace in foreground console mode...
"%PYTHON%" -m uvicorn app.main:app --host %HOST% --port %PORT%
exit /b %errorlevel%

:check_server
set "IS_RUNNING=0"
where curl >nul 2>&1
if %errorlevel% equ 0 (
    curl -s -f -m 1 "%APP_URL%/api/config" >nul 2>&1
    if !errorlevel! equ 0 set "IS_RUNNING=1"
) else (
    powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri '%APP_URL%/api/config' -TimeoutSec 1 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
    if !errorlevel! equ 0 set "IS_RUNNING=1"
)
exit /b 0

:check_port
set "PORT_BUSY=0"
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort %1 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 set "PORT_BUSY=1"
exit /b 0

:check_process_alive
set "PROC_ALIVE=1"
powershell -NoProfile -Command "if (Get-Process -Id %1 -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>&1
if %errorlevel% neq 0 set "PROC_ALIVE=0"
exit /b 0
