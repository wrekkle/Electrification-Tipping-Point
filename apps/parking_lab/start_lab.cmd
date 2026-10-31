@echo off
cd /d "%~dp0..\.."
python -m apps.parking_lab.workbench serve %*
if errorlevel 1 pause
