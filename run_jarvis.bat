@echo off
REM Run the Jarvis PowerShell script from this folder
pushd "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_jarvis.ps1" %*
set "exitCode=%ERRORLEVEL%"
popd
exit /b %exitCode%
