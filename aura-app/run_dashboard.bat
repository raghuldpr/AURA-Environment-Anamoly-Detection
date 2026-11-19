@echo off
REM Starts the AURA dashboard. Close the PlatformIO serial monitor first (one program per COM port).
cd /d "%~dp0"
venv\Scripts\streamlit.exe run app.py
