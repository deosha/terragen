#!/bin/bash

# TerraGen - Start API and Frontend

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}Starting TerraGen...${NC}"

# Check .env
if [ ! -f .env ]; then
    echo "Error: .env file not found. Copy .env.example to .env and fill in your keys."
    exit 1
fi

# Export env vars for frontend
export $(grep -v '^#' .env | grep NEXT_PUBLIC | xargs)

# Kill existing processes on ports 8000 and 3000
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:3000 | xargs kill -9 2>/dev/null || true

# Start API in background
echo -e "${BLUE}Starting API on http://localhost:8000${NC}"
cd "$SCRIPT_DIR"
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!

# Wait for API to be ready
sleep 2

# Clear Next.js cache to avoid stale files
echo -e "${BLUE}Clearing Next.js cache...${NC}"
rm -rf "$SCRIPT_DIR/web/.next"

# Start Frontend
echo -e "${BLUE}Starting Frontend on http://localhost:3000${NC}"
cd "$SCRIPT_DIR/web"
npm run dev &
WEB_PID=$!

echo ""
echo -e "${GREEN}TerraGen is running!${NC}"
echo "  API:      http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop"

# Handle shutdown
trap "kill $API_PID $WEB_PID 2>/dev/null; exit" SIGINT SIGTERM

# Wait for processes
wait
