from pydantic import BaseModel

class DatabaseStatus(BaseModel):
    """Nested model for database health indicator."""
    connected: bool

class HealthResponse(BaseModel):
    """Main response model for system health reporting."""
    status: str
    database: DatabaseStatus
