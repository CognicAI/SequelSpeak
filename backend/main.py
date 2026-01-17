from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.v1 import connection

app = FastAPI(title="Backend API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(connection.router, prefix="/api/v1/utils", tags=["Utils"])

@app.get("/")
async def root():
    return {"status": "ok"}
