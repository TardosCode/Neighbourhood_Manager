@echo off
REM ============================================================
REM Hay Day Helper - Windows .exe builder
REM
REM Run this from the project root after installing Python.
REM It installs the required packages and produces dist\HayDayHelper.exe
REM ============================================================

echo.
echo Step 1: installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo.
echo Step 2: building the exe...
python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name HayDayHelper ^
    --add-data "assets;assets" ^
    --noconfirm ^
    src\main.py

echo.
echo Done! The .exe is in dist\HayDayHelper.exe
echo.
echo To use it:
echo   1. Copy dist\HayDayHelper.exe to a folder of your choice
echo   2. The 'profiles' folder will be created next to the .exe on first run
echo.
pause
