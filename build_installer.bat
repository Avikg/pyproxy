@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo  PyProxy - Build Installer
echo ============================================================
echo.

:: Check Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    pause & exit /b 1
)

:: Check Inno Setup
set ISCC=""
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"       set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
if %ISCC%=="" (
    echo [ERROR] Inno Setup 6 not found.
    echo Download from: https://jrsoftware.org/isdl.php
    pause & exit /b 1
)

:: Setup venv
echo [1/3] Setting up virtual environment...
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install PyYAML pystray Pillow --quiet

:: Build installer
echo [2/3] Building installer with Inno Setup...
if not exist installer_output mkdir installer_output
%ISCC% pyproxy_installer.iss
if errorlevel 1 (
    echo [ERROR] Inno Setup build failed.
    pause & exit /b 1
)

echo [3/3] Done!
echo.
echo ============================================================
echo  BUILD SUCCESSFUL
echo  Installer: installer_output\PyProxySetup.exe
echo.
echo  Send this file to any Windows machine with Python installed.
echo  The installer handles everything else automatically.
echo ============================================================
echo.
pause
