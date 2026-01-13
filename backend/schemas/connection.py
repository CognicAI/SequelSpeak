from pydantic import BaseModel, Field

class ConnectionRequest(BaseModel):
    connection_url: str = Field(..., min_length=1, description="The PostgreSQL connection URL string")
