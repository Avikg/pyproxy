@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo  PyProxy - Build Standalone Executable
echo ============================================================
echo.

:: Check Python is available
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)

echo [1/5] Creating virtual environment...
if exist .venv (
    echo       .venv already exists, skipping creation.
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo [2/5] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [3/5] Installing dependencies...
python -m pip install --upgrade pip --quiet
pip install PyYAML pystray Pillow pyinstaller --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo [4/5] Building executable with PyInstaller...
if exist dist\PyProxy.exe del /f dist\PyProxy.exe
if exist build rmdir /s /q build

pyinstaller pyproxy.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

echo [5/5] Copying config to dist folder...
if not exist dist\config.yaml (
    copy config.yaml dist\config.yaml >nul
)

echo.
echo ============================================================
echo  BUILD SUCCESSFUL
echo  Output: dist\PyProxy.exe
echo.
echo  To distribute:
echo    Copy the entire dist\ folder to any Windows machine.
echo    Run PyProxy.exe - it will appear in the system tray.
echo ============================================================
echo.
pause
