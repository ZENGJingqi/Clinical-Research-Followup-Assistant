@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Run setup_public_windows.bat first.
  exit /b 1
)

".venv\Scripts\python.exe" manage.py runserver 0.0.0.0:8000
