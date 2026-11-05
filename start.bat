@echo off
setlocal
cd /d "%~dp0"

set "APP_URL=http://127.0.0.1:8000"
set "PID_FILE=%~dp0data\tidetrace-server.pid"

if not exist "%~dp0data" mkdir "%~dp0data"

rem If the app is already serving on the expected port, just open it.
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $c=Invoke-RestMethod -Uri '%APP_URL%/api/config' -TimeoutSec 2; if($c.codename -eq 'TideTrace'){exit 0} else {exit 2} } catch {exit 1}"
if not errorlevel 1 (
  echo TideTrace is already running. Opening %APP_URL%
  start "" "%APP_URL%"
  exit /b 0
)

rem Do not start over another service already using port 8000.
powershell -NoProfile -ExecutionPolicy Bypass -Command "if(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue){exit 0}else{exit 1}"
if not errorlevel 1 (
  echo Port 8000 is in use by another app. Close it or change the port before starting TideTrace.
  pause
  exit /b 1
)

set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=%~dp0venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON_PATH set "PYTHON_PATH=%%P"
  if not defined PYTHON_PATH (
    echo Python was not found. Install Python or create a venv first.
    pause
    exit /b 1
  )
  set "PYTHON=%PYTHON_PATH%"
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $root=(Resolve-Path -LiteralPath '%~dp0').Path; $python='%PYTHON%'; $pidFile=Join-Path $root 'data\tidetrace-server.pid'; $out=Join-Path $root 'data\server.log'; $err=Join-Path $root 'data\server-error.log'; $p=Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput $out -RedirectStandardError $err; Set-Content -LiteralPath $pidFile -Value @($p.Id,$python)"
if errorlevel 1 (
  echo Could not launch the app. Check Python and data\server-error.log.
  pause
  exit /b 1
)

echo Starting TideTrace...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ready=$false; for($i=0; $i -lt 30; $i++){ try { $c=Invoke-RestMethod -Uri '%APP_URL%/api/config' -TimeoutSec 2; if($c.codename -eq 'TideTrace'){$ready=$true; break} } catch {}; Start-Sleep -Seconds 1 }; if($ready){exit 0}else{exit 1}"
if errorlevel 1 (
  echo The app did not become ready. Check data\server-error.log.
  pause
  exit /b 1
)

echo TideTrace is ready. Opening %APP_URL%
start "" "%APP_URL%"
exit /b 0
