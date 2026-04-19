#!/bin/bash
# JARVIS – one-command start / restart

echo "🛑 Stopping existing processes..."
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:5173 | xargs kill -9 2>/dev/null
sleep 1

echo "🚀 Starting backend..."
source /Users/adela/Jarvis/backend/venv/bin/activate
cd /Users/adela/Jarvis/backend
python main.py &
BACKEND_PID=$!
sleep 2

echo "🎨 Starting frontend..."
cd /Users/adela/Jarvis/frontend
npm run dev &
FRONTEND_PID=$!
sleep 2

echo ""
echo "✅ JARVIS is running!"
echo "   Backend  → http://localhost:8000  (pid $BACKEND_PID)"
echo "   Frontend → http://localhost:5173  (pid $FRONTEND_PID)"
echo ""
echo "Press Ctrl+C to stop both."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo '🛑 Stopped.'; exit" INT TERM
wait
