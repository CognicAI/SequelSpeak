from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from pathlib import Path

# Get the directory where this config file is located
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=str(ENV_FILE), env_file_encoding='utf-8')
    
    app_name: str = "FastAPI Backend"
    environment: str = "development"
    db_connection_timeout: int = 10  # Database connection timeout in seconds

settings = Settings()
