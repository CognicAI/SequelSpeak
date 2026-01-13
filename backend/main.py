from fastapi import FastAPI

app = FastAPI(title="Backend API")

@app.get("/")
async def root():
    return {"status": "ok"}
