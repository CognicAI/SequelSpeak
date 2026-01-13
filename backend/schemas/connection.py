from pydantic import BaseModel, Field

class ConnectionRequest(BaseModel):
    connection_url: str = Field(..., description="The PostgreSQL connection URL string")
