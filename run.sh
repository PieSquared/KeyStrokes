#!/usr/bin/env bash

set -e

echo "Creating virtual environment..."
python3 -m venv .venv

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Upgrading pip..."
python -m pip install --upgrade pip

echo "Installing requirements..."
python -m pip install -r requirements.txt

echo
echo "Launching KeyStroke.pyw..."
python KeyStroke.pyw &

echo
echo "Done!"
echo "The application is now running."