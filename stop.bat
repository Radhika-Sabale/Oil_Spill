@echo off
setlocal
set "PID_FILE=%~dp0data\tidetrace-server.pid"

if not exist "%PID_FILE%" (
  echo No TideTrace server PID file found. The server may already be stopped.
  exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $pidFile='%PID_FILE%'; $lines=Get-Content -LiteralPath $pidFile; $procId=0; if($lines.Count -lt 2 -or -not [int]::TryParse($lines[0],[ref]$procId)){Write-Host 'PID file is invalid; leaving processes untouched.'; exit 1}; $connections=@(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue); if(-not ($connections | Where-Object {$_.OwningProcess -eq $procId})){Write-Host 'The recorded process is not listening on port 8000. Leaving it untouched.'; exit 1}; $c=Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/config' -TimeoutSec 3; if($c.codename -ne 'TideTrace'){Write-Host 'The service on port 8000 is not TideTrace. Leaving it untouched.'; exit 1}; Stop-Process -Id $procId -Force; Remove-Item -LiteralPath $pidFile -Force; Write-Host 'TideTrace server stopped.'"
if errorlevel 1 (
  echo Stop was skipped. The process did not match the recorded TideTrace server.
  pause
  exit /b 1
)
exit /b 0
