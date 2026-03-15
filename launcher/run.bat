@echo off
:: PyProxy Launcher
:: This file is placed in the install directory and called by the Start Menu shortcut.
:: It runs tray_app.py using pythonw (no console window).

cd /d "%~dp0"
start "" pythonw "%~dp0tray_app.py"
