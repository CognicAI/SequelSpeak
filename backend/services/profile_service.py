import logging
import hashlib
from typing import List, Optional
from sqlmodel import Session, select, SQLModel
from datetime import datetime
import uuid

from config import settings
from models.profile import Profile
from schemas.profile import ProfileCreate, ProfileUpdate, ProfileResponse
from utils.db import engine

logger = logging.getLogger(__name__)

class ProfileService:
    def __init__(self):
        # We'll use this to cache the initialize() result if needed
        pass

    async def initialize(self) -> None:
        """
        Initialize the database tables if they don't exist.
        """
        try:
            SQLModel.metadata.create_all(engine)
            logger.info("PostgreSQL tables initialized (if they didn't exist)")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL tables: {e}")

    async def close(self) -> None:
        """Database engine is managed globally, no specific close needed per service."""
        pass

    async def get_profiles(self, user_id: str) -> List[ProfileResponse]:
        with Session(engine) as session:
            statement = select(Profile).where(Profile.user_id == user_id)
            profiles = session.exec(statement).all()
            
            return [
                ProfileResponse(
                    id=p.id,
                    name=p.name,
                    host=p.host,
                    port=p.port,
                    username=p.username,
                    database=p.database,
                    createdAt=p.created_at.isoformat().replace('+00:00', 'Z'),
                    lastUsed=p.last_used.isoformat().replace('+00:00', 'Z') if p.last_used else None
                ) for p in profiles
            ]

    async def get_profile(self, user_id: str, profile_id: str) -> Optional[Profile]:
        """Returns the Profile model instance."""
        with Session(engine) as session:
            statement = select(Profile).where(
                Profile.user_id == user_id, 
                Profile.id == profile_id
            )
            return session.exec(statement).first()

    async def get_decrypted_password(self, user_id: str, profile_id: str) -> Optional[str]:
        """
        DEPRECATED in ProfileService. 
        Passwords are no longer stored in PostgreSQL.
        Use CredentialCacheService instead.
        """
        return None

    async def create_profile(self, user_id: str, profile_in: ProfileCreate) -> ProfileResponse:
        db_profile = Profile(
            user_id=user_id,
            name=profile_in.name,
            host=profile_in.host,
            port=profile_in.port,
            username=profile_in.username,
            database=profile_in.database
        )
        
        with Session(engine) as session:
            session.add(db_profile)
            session.commit()
            session.refresh(db_profile)
            
            return ProfileResponse(
                id=db_profile.id,
                name=db_profile.name,
                host=db_profile.host,
                port=db_profile.port,
                username=db_profile.username,
                database=db_profile.database,
                createdAt=db_profile.created_at.isoformat().replace('+00:00', 'Z'),
                lastUsed=None
            )

    async def update_profile(self, user_id: str, profile_id: str, profile_in: ProfileUpdate) -> Optional[ProfileResponse]:
        with Session(engine) as session:
            statement = select(Profile).where(
                Profile.user_id == user_id, 
                Profile.id == profile_id
            )
            db_profile = session.exec(statement).first()
            if not db_profile:
                return None
            
            update_data = profile_in.model_dump(exclude_unset=True)
            
            # We explicitly ignore password in the profile update for DB persistence
            update_data.pop("password", None)
            
            # Map camelCase to snake_case if necessary
            if "lastUsed" in update_data:
                val = update_data.pop("lastUsed")
                if val:
                    try:
                        dt_str = val.replace('Z', '+00:00')
                        update_data["last_used"] = datetime.fromisoformat(dt_str)
                    except ValueError:
                        pass
            
            for key, value in update_data.items():
                if hasattr(db_profile, key):
                    setattr(db_profile, key, value)
            
            session.add(db_profile)
            session.commit()
            session.refresh(db_profile)
            
            return ProfileResponse(
                id=db_profile.id,
                name=db_profile.name,
                host=db_profile.host,
                port=db_profile.port,
                username=db_profile.username,
                database=db_profile.database,
                createdAt=db_profile.created_at.isoformat().replace('+00:00', 'Z'),
                lastUsed=db_profile.last_used.isoformat().replace('+00:00', 'Z') if db_profile.last_used else None
            )

    async def delete_profile(self, user_id: str, profile_id: str) -> bool:
        with Session(engine) as session:
            statement = select(Profile).where(
                Profile.user_id == user_id, 
                Profile.id == profile_id
            )
            db_profile = session.exec(statement).first()
            if not db_profile:
                return False
            
            session.delete(db_profile)
            session.commit()
            return True

profile_service = ProfileService()
