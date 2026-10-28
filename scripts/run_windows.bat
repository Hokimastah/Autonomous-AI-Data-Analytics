@echo off
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
  echo Python virtual environment not found. See README.
  exit /b 1
)
.venv\Scripts\python.exe main.py run
