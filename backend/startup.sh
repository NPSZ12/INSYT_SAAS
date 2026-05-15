#!/bin/bash

echo "Starting INSYT API..."
cd /home/site/wwwroot

echo "Current directory:"
pwd

echo "Files:"
ls -la

export PYTHONPATH="/home/site/wwwroot"

echo "Installing runtime dependencies if needed..."
python -m pip install -r requirements.txt

echo "Starting FastAPI..."
exec python -m uvicorn main:app --host 0.0.0.0 --port 8000