#!/bin/bash
set -e

echo "Starting INSYT API..."
cd /home/site/wwwroot

echo "Current directory:"
pwd

echo "Files:"
ls -la

echo "Installing dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "Starting uvicorn..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000