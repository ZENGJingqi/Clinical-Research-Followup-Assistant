@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Run setup_windows.bat first.
  exit /b 1
)

".venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000
