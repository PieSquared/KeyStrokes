@echo off
echo Installing required Python packages...

:: Upgrade pip
python -m pip install --upgrade pip

:: Install all required packages
pip install PyQt5 pynput psutil GPUtil

echo.
echo All packages installed successfully.
pause
