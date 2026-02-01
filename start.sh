#!/bin/bash

# SequelSpeak Startup Script
# Launches both frontend and backend servers concurrently

# Color codes for output
GREEN='\033[0;32m'
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

# Start backend
echo -e "${GREEN}[Backend]${NC} Starting FastAPI server..."
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!
cd ..

# Wait a moment for backend to initialize
sleep 2

# Start frontend
echo -e "${GREEN}[Frontend]${NC} Starting Vite dev server..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

# Display status
echo -e "\n${GREEN}✓${NC} SequelSpeak is running!"
echo -e "${GREEN}Frontend:${NC} http://localhost:5173"
echo -e "${GREEN}Backend:${NC}  http://localhost:8000"
echo -e "${GREEN}API Docs:${NC} http://localhost:8000/docs"
echo -e "\n${YELLOW}Press Ctrl+C to stop all servers${NC}\n"

# Wait for both processes
wait
