@echo off
cd /d "%~dp0"
title Orion - Governed AI Coding Agent v6.4.0

REM ============================================
REM  ORION - Single Launcher (v6.4.0)
REM  Usage:
REM    Orion.bat          (interactive menu)
REM    Orion.bat cli      (terminal interface)
REM    Orion.bat web      (browser interface)
REM    Orion.bat api      (API server only)
REM ============================================

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python is not installed or not in PATH
    echo  Install Python 3.10+ from https://python.org
    echo.
    pause
    exit /b 1
)

REM Launch
python launch.py %*

REM Keep window open on error
if errorlevel 1 (
    echo.
    echo  Orion exited with an error. Check the output above.
    pause
)
