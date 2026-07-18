#!/usr/bin/env bash
set -e

echo "→ Python venv"
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .

echo "→ Web client deps"
cd q1-voice-agent/web-client
npm install
cd ../..

echo "✓ Setup complete"
