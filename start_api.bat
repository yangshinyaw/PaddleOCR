@echo off
REM Quick Start Script for Receipt OCR API
REM This script installs dependencies and starts the server

echo ============================================================
echo Receipt OCR API - Quick Start
echo ============================================================
echo.

REM Check if virtual environment exists
if not exist "venv\" (
    echo ERROR: Virtual environment not found!
    echo Please run setup.sh first to create virtual environment
    pause
    exit /b 1
)

echo [1/3] Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo [2/3] Installing Week 2 dependencies...
pip install -q -r requirements-week2.txt

echo.
echo [3/3] Starting API server...
echo.
echo ============================================================
echo API Server Starting
echo ============================================================
echo.
echo Access API at: http://localhost:8000
echo API Documentation: http://localhost:8000/docs
echo Test Page: Open test_page.html in your browser
echo.
echo Press Ctrl+C to stop the server
echo ============================================================
echo.

python main.py
