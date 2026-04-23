@echo off
setlocal
cd /d "%~dp0"

set /p PUBLIC_HOSTS=请输入公网访问域名或IP（多个用逗号分隔）:
if "%PUBLIC_HOSTS%"=="" (
  echo 未输入公网域名/IP，已取消。
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
    echo 未检测到 Python，请先安装 Python 3.11+ 并勾选 Add Python to PATH。
    exit /b 1
  )
)

