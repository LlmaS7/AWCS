@echo off
title AWCS
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Please create .venv and install requirements.txt first.
  pause
  exit /b 1
)
if "%~1"=="" (
  start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py" --map fleet_64x64 --robots 16
) else (
  "%~dp0.venv\Scripts\python.exe" "%~dp0main.py" %*
  if errorlevel 1 pause
)

