@echo off
cd /d "%~dp0"
py -3.11 -m venv .venv
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pip install -e .
if errorlevel 1 exit /b 1
echo Setup complete. Read START_HERE.md to set your Gemini key and run.
