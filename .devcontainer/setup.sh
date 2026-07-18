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

echo "→ Starting Qdrant"
docker run -d --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v "$(pwd)/qdrant_storage:/qdrant/storage" \
  qdrant/qdrant

echo "✓ Done. Run: source .venv/bin/activate"
