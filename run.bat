@echo off
setlocal

echo Creating virtual environment...
py -m venv .venv

echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing requirements...
python -m pip install -r requirements.txt

echo.
echo Launching KeyStroke.pyw...
start "" pythonw KeyStroke.pyw

exit /b