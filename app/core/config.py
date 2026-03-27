import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "WinStake.ia"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "un-secreto-muy-seguro-para-desarrollo")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Database
    # Recomendación: usar URL robusta. Ejemplo: postgresql://user:pass@localhost:5432/winstake
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/winstake")

    class Config:
        env_file = ".env"

settings = Settings()
