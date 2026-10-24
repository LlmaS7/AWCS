@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3 -m venv "%~dp0.venv"
  ) else (
    python -m venv "%~dp0.venv"
  )
  if errorlevel 1 goto failed
)
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto failed
echo Setup complete. Run launch.bat to start AWCS.
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.14 x64 with pip and retry.
pause
exit /b 1
