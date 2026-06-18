@echo off
title WBSEDCL - Build Standalone EXE
color 0A
echo.
echo  =============================================
echo   WBSEDCL Receive Section - Build Tool
echo  =============================================
echo.

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Please install Python 3.8+ and add to PATH.
    pause
    exit /b 1
)

echo  [1/4] Installing / upgrading PyInstaller...
pip install --quiet --upgrade pyinstaller
if errorlevel 1 (
    echo  [ERROR] Failed to install PyInstaller.
    pause
    exit /b 1
)

echo  [2/4] Installing app dependencies...
pip install --quiet flask PyJWT bcrypt
if errorlevel 1 (
    echo  [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo  [3/4] Building executable (this may take 1-3 minutes)...
python -m PyInstaller WBSEDCL.spec --noconfirm
if errorlevel 1 (
    echo  [ERROR] Build failed. See output above for details.
    pause
    exit /b 1
)

echo  [4/4] Packaging distributable...
if exist "WBSEDCL_Release" rmdir /s /q "WBSEDCL_Release"
mkdir "WBSEDCL_Release"
copy /y "dist\WBSEDCL.exe" "WBSEDCL_Release\WBSEDCL.exe"

echo.
echo  =============================================
echo   BUILD COMPLETE!
echo  =============================================
echo.
echo  Output: WBSEDCL_Release\WBSEDCL.exe  (single file, no dependencies)
echo.
echo  To deploy to another PC:
echo    1. Copy just "WBSEDCL.exe" to any folder on the other machine
echo    2. Double-click it
echo    3. Browser opens automatically to http://localhost:3000
echo    4. The database (wbsedcl.db) is saved in the same folder as the exe
echo.
echo  Default login:  admin / admin123
echo.
pause
