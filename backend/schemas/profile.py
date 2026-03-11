from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class ProfileBase(BaseModel):
    name: str
    host: str
    port: str
    username: str
    database: str

class ProfileCreate(ProfileBase):
    password: str

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[str] = None
    username: Optional[str] = None
    database: Optional[str] = None
    password: Optional[str] = None
    lastUsed: Optional[str] = None

class ProfileResponse(ProfileBase):
    id: str
    createdAt: str
    lastUsed: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True,
    )
