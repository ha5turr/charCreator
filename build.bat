@echo off
rem Пересборка WoWCharAuto.exe (нужен Python + pip install pyautogui pygetwindow pillow pyinstaller)
pyinstaller --onefile --windowed --name "WoWCharAuto" wow_char_auto.py
pause
