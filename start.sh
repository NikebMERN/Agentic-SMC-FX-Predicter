#!/usr/bin/env bash
# SmartFlow AI — one command starts the full platform
set -e
cd "$(dirname "$0")"
pip install -r requirements.txt -q
exec python run.py start
