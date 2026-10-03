@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Create the environment first: py -3 -m venv .venv
  echo Then install dependencies from requirements-lock.txt
  pause
  exit /b 1
)
echo Checking ResearchPilot environment and data...
".venv\Scripts\python.exe" -m researchpilot.maintenance doctor
if errorlevel 1 (
  pause
  exit /b 1
)
echo ResearchPilot: http://127.0.0.1:8765
".venv\Scripts\python.exe" -m uvicorn researchpilot.app:app --host 127.0.0.1 --port 8765
pause
