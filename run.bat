@echo off
cd /d %~dp0
where python >nul 2>&1 || (echo Python belum terinstall. Install dari python.org atau Microsoft Store. & pause & exit /b 1)
python -m pip install -q -r requirements.txt
python panel.py
pause
