#!/bin/bash

# SequelSpeak Startup Script
# Launches both frontend and backend servers concurrently

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting SequelSpeak...${NC}"

# Function to handle cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Shutting down servers...${NC}"
    kill $(jobs -p) 2>/dev/null
    exit 0
}

# Trap SIGINT (Ctrl+C) and SIGTERM
trap cleanup SIGINT SIGTERM

# Check backend venv exists
if [ ! -d ".venv" ]; then
    echo -e "${RED}Error: .venv not found.${NC}"
    echo -e "${YELLOW}Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r backend/requirements.txt${NC}"
    exit 1
fi

# Check if port 8000 is available
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${RED}Error: Port 8000 is already in use${NC}"
    echo -e "${YELLOW}Stop the existing process or use a different port${NC}"
    exit 1
fi

# Start backend
echo -e "${GREEN}[Backend]${NC} Starting FastAPI server..."
source .venv/bin/activate
cd backend
uvicorn main:app --reload --port 8000 --host 0.0.0.0 &
BACKEND_PID=$!
cd ..

# Wait a moment for backend to initialize
sleep 2

# Verify backend started successfully
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo -e "${RED}Error: Backend failed to start${NC}"
    exit 1
fi

# Check frontend dependencies
if [ ! -d "frontend/node_modules" ]; then
    echo -e "${YELLOW}Warning: node_modules not found. Running npm install...${NC}"
    cd frontend
    npm install
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: npm install failed${NC}"
        kill $BACKEND_PID 2>/dev/null
        exit 1
    fi
    cd ..
fi

# Start frontend
echo -e "${GREEN}[Frontend]${NC} Starting Vite dev server..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

# Verify frontend started successfully
if ! kill -0 $FRONTEND_PID 2>/dev/null; then
    echo -e "${RED}Error: Frontend failed to start${NC}"
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

# Display status
echo -e "\n${GREEN}✓${NC} SequelSpeak is running!"
echo -e "${GREEN}Frontend:${NC} http://localhost:5173"
echo -e "${GREEN}Backend:${NC}  http://localhost:8000"
echo -e "${GREEN}API Docs:${NC} http://localhost:8000/docs"
echo -e "\n${YELLOW}Press Ctrl+C to stop all servers${NC}\n"

# Wait for both processes
wait
