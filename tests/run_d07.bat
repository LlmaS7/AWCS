@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Project Python not found: .venv\Scripts\python.exe
  pause
  exit /b 2
)
".venv\Scripts\python.exe" -B "tests\run_d07.py" %*
set "d07_result=%ERRORLEVEL%"
echo.
echo Exit code: %d07_result%  ^(0=state checks passed, 1=failed, 2=inconclusive^)
pause
exit /b %d07_result%
