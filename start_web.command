#!/bin/bash
cd "$(dirname "$0")"

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
else
  echo "Python was not found. Please install Python 3 and try again."
  read -r -p "Press Enter to close..."
  exit 1
fi

$PYTHON_CMD scripts/bilibili_web.py
STATUS=$?
if [ "$STATUS" -ne 0 ]; then
  echo
  echo "Web UI stopped with an error."
fi
read -r -p "Press Enter to close..."
