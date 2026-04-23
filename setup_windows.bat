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
    echo 未检测到 Python，请先安装 Python 3.11+ 并勾选 Add Python to PATH。
    exit /b 1
  )
)
