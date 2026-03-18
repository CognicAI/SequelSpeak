#!/bin/bash

# SequelSpeak Startup Script
# Launches both frontend and backend servers concurrently

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Starting SequelSpeak...${NC}"

cleanup() {
    echo -e "\n${YELLOW}Shutting down servers...${NC}"
    kill $(jobs -p) 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

# Check backend folder exists
if [ ! -d "backend" ]; then
    echo -e "${RED}Error: backend folder not found.${NC}"
    exit 1
fi

# Check venv inside backend
if [ ! -d "backend/.venv" ]; then
    echo -e "${RED}Error: .venv not found in backend folder.${NC}"
    echo -e "${YELLOW}Run: cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt${NC}"
    exit 1
fi

# Check port 8000
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${RED}Error: Port 8000 is already in use${NC}"
    exit 1
fi

####################################
# Start Backend
####################################
echo -e "${GREEN}[Backend]${NC} Starting FastAPI server..."

cd backend || exit 1

source .venv/bin/activate

uvicorn main:app --reload --port 8000 --host 0.0.0.0 &
BACKEND_PID=$!

cd ..

sleep 2

####################################
# Start Frontend
####################################
if [ ! -d "frontend/node_modules" ]; then
    echo -e "${YELLOW}Installing frontend dependencies...${NC}"
    cd frontend || exit 1
    npm install || { echo -e "${RED}npm install failed${NC}"; kill $BACKEND_PID; exit 1; }
    cd ..
fi

echo -e "${GREEN}[Frontend]${NC} Starting Vite dev server..."

cd frontend || exit 1
npm run dev &
FRONTEND_PID=$!
cd ..

####################################
# Status
####################################
echo -e "\n${GREEN}✓${NC} SequelSpeak is running!"
echo -e "${GREEN}Frontend:${NC} http://localhost:5173"
echo -e "${GREEN}Backend:${NC}  http://localhost:8000"
echo -e "${GREEN}API Docs:${NC} http://localhost:8000/docs"
echo -e "\n${YELLOW}Press Ctrl+C to stop all servers${NC}\n"

wait