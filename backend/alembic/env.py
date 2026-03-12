import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# ---------------------------------------------------------------------------
# Make sure the backend package root is importable regardless of where alembic
# is invoked from (e.g. `cd backend && alembic upgrade head`).
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

# Import every model module so their tables are registered with SQLModel.metadata
# before Alembic compares metadata against the live schema.
import models.profile  # noqa: F401, E402  # pyright: ignore[reportUnusedImport]

# ---------------------------------------------------------------------------
# Alembic Config object (gives access to values in alembic.ini)
# ---------------------------------------------------------------------------
config = context.config

# Override the URL with the value from application settings so credentials
# are never stored in alembic.ini.
#
# Resolution order:
#   1. ALEMBIC_DATABASE_URL env var  — use this when running migrations locally
#      (the internal_database_url uses the Docker hostname "db" which only
#       resolves inside the container network)
#   2. settings.internal_database_url — used at runtime when inside Docker
#   3. Hard-coded Docker fallback (last resort)
_db_url = (
    os.environ.get("ALEMBIC_DATABASE_URL")
    or settings.internal_database_url
    or "postgresql+psycopg://postgres:postgres@db:5432/sequelspeak"
)
config.set_main_option("sqlalchemy.url", _db_url)

# Set up logging as defined in alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The SQLModel metadata that Alembic will diff against the live database
target_metadata = SQLModel.metadata


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emits SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
