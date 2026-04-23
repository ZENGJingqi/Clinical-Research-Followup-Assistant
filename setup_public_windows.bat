@echo off
setlocal
cd /d "%~dp0"

set /p PUBLIC_HOSTS=Enter public host or IP (comma-separated if multiple): 
if "%PUBLIC_HOSTS%"=="" (
  echo No public host or IP was provided. Setup cancelled.
  exit /b 1
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 one_click_setup.py --mode public --public-hosts "%PUBLIC_HOSTS%"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    python one_click_setup.py --mode public --public-hosts "%PUBLIC_HOSTS%"
  ) else (
    echo Python was not found. Please install Python 3.11+ and add it to PATH.
    exit /b 1
  )
)
