@echo off
title Counter Siege - Tactical FPS
echo ================================
echo   COUNTER SIEGE - Tactical FPS
echo ================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Please install Python 3.8+ from https://python.org
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b
)

python -c "import cv2" >nul 2>&1
if errorlevel 1 (
    echo Installing required packages...
    pip install opencv-python numpy
)

echo Starting Counter Siege...
python counter_siege.py %*
pause
