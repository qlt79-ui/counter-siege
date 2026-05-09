@echo off
title CS 1.6 Clone
echo ================================
echo     CS 1.6 CLONE  —  Setup
echo ================================
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://python.org
    echo Make sure to check "Add Python to PATH"
    pause & exit /b
)
python -c "import cv2" >nul 2>&1
if errorlevel 1 (
    echo Installing opencv-python...
    pip install opencv-python numpy
)
echo Launching game...
python cs16_clone.py %*
pause
