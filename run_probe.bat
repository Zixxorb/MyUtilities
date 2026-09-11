@echo off
REM Double-click this. It runs probe_v2.py from the same folder and keeps the
REM window open so you can read the output.
cd /d "%~dp0"

if not exist "probe_v2.py" (
  echo.
  echo probe_v2.py was not found in this folder:
  echo   %~dp0
  echo.
  echo Both run_probe.bat AND probe_v2.py need to be in the same directory.
  echo If you see an older probe_myusage.py here, you can delete it - it is
  echo not used any more.
  echo.
  pause
  exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found on your PATH.
  echo Install it from https://www.python.org/downloads/ and tick
  echo "Add python.exe to PATH" during setup.
  pause
  exit /b 1
)

python -c "import requests" >nul 2>&1
if errorlevel 1 (
  echo Installing the requests library...
  python -m pip install requests
)

echo.
python probe_v2.py
echo.
pause
