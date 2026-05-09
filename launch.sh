#!/bin/bash
echo "================================"
echo "    CS 1.6 CLONE  —  Setup"
echo "================================"
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 not found. Install Python 3.8+ from python.org"; exit 1
fi
python3 -c "import cv2" 2>/dev/null || pip3 install opencv-python numpy
echo "Launching game..."
python3 cs16_clone.py "$@"
