@echo off
title WBSEDCL Receive Section
echo.
echo  =============================================
echo   WBSEDCL Receive Section Management System
echo  =============================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Python is not installed!
    echo  Download from: https://www.python.org/downloads/
    echo  During install, check "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

pip show flask >nul 2>&1
if %errorlevel% neq 0 (
    echo  Installing dependencies - please wait...
    pip install flask bcrypt PyJWT
    echo.
)

echo  Starting server at http://localhost:3000
echo  Press Ctrl+C to stop.
echo.
echo  Default Login:  admin / admin123
echo.

start http://localhost:3000
python app.py
pause
