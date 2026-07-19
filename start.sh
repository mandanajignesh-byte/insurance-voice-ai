#!/usr/bin/env bash
set -e
cd /workspaces/insurance-voice-ai
source .venv/bin/activate

echo "→ Starting Qdrant..."
./qdrant > /tmp/qdrant.log 2>&1 &
sleep 2

echo "→ Loading KB into Qdrant..."
cd q2-knowledge-base
python -m retrieval.load_qdrant > /tmp/kb_load.log 2>&1
cd ..

echo "→ Starting KB API..."
cd q2-knowledge-base
uvicorn retrieval.api:app --port 8000 > /tmp/kb_api.log 2>&1 &
cd ..
sleep 3

echo "→ Starting Q1 Agent (Priya)..."
cd q1-voice-agent/agent
python agent.py > /tmp/agent.log 2>&1 &
cd ../..
sleep 2

echo "→ Starting Web Client..."
cd q1-voice-agent/web-client
npm run dev -- --host > /tmp/vite.log 2>&1 &
cd ../..

echo "→ Starting Q4 Insights Server..."
cd q4-realtime/streaming
python server.py > /tmp/q4.log 2>&1 &
cd ../..

echo ""
echo "✓ All services started!"
echo "  Q1 Web Client : http://localhost:5173"
echo "  Q1 Agent WS   : http://localhost:7860"
echo "  KB API        : http://localhost:8000"
echo "  Q4 Dashboard  : http://localhost:7864"
echo "  Qdrant        : http://localhost:6333"
echo ""
echo "Logs: /tmp/*.log"
echo "Stop all: pkill -f 'agent.py|uvicorn|qdrant|vite|server.py'"
