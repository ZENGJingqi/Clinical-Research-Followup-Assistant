@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 one_click_setup.py --mode local
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    python one_click_setup.py --mode local
  ) else (
    echo Python was not found. Please install Python 3.11+ and add it to PATH.
    exit /b 1
  )
)
