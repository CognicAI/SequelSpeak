from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from alembic.config import Config
from alembic import command
from config import settings
import logging

logger = logging.getLogger(__name__)

# Use the internal database URL from settings
database_url = settings.internal_database_url or "postgresql+psycopg://postgres:postgres@db:5432/sequelspeak"

# Async engine for all runtime DB operations.
# Alembic uses its own sync engine created inside alembic/env.py.
async_engine = create_async_engine(database_url, echo=settings.environment == "development")

# Absolute path to alembic.ini sitting next to this package's parent (backend/)
_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"


def run_migrations() -> None:
    """Apply all pending Alembic migrations up to the latest revision."""
    logger.info("Running Alembic migrations...")
    alembic_cfg = Config(str(_ALEMBIC_INI))
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic migrations complete")


async def get_session():
    """FastAPI dependency for an async database session."""
    async with AsyncSession(async_engine) as session:
        yield session
