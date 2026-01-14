from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")
    
    app_name: str = "FastAPI Backend"
    environment: str = "development"
    db_connection_timeout: int = 10  # Database connection timeout in seconds

settings = Settings()
