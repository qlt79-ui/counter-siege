#!/bin/bash
# Counter Siege Launcher
echo "================================"
echo "  COUNTER SIEGE - Tactical FPS"
echo "================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found. Install Python 3.8+ from python.org"
    exit 1
fi

# Check OpenCV
if ! python3 -c "import cv2" 2>/dev/null; then
    echo "Installing required dependency (opencv-python)..."
    pip3 install opencv-python numpy
fi

echo "Starting Counter Siege..."
python3 counter_siege.py "$@"
