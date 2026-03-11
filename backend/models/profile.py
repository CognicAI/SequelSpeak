from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field
import uuid

class Profile(SQLModel, table=True):
    __tablename__ = "profiles"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(index=True)
    name: str
    host: str
    port: str
    username: str
    database: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    last_used: Optional[datetime] = None
