from sqlmodel import create_engine, Session, SQLModel
from config import settings
import logging

logger = logging.getLogger(__name__)

# Use the internal database URL from settings
database_url = settings.internal_database_url or "postgresql+psycopg://postgres:postgres@db:5432/sequelspeak"

engine = create_engine(database_url, echo=settings.environment == "development")

def init_db():
    """Initialize the database (create tables if they don't exist)."""
    # In production, we should use Alembic migrations instead of SQLModel.metadata.create_all
    SQLModel.metadata.create_all(engine)

def get_session():
    """Dependency for getting a database session."""
    with Session(engine) as session:
        yield session
