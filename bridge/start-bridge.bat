@echo off
cd /d "%~dp0"
"..\qq-service\.venv\Scripts\python.exe" bridge.py
if errorlevel 1 pause
