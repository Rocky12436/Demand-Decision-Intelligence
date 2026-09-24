from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os
from pathlib import Path

# Look for .env file in project root or backend/.env
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILES = [str(PROJECT_ROOT / ".env"), str(BACKEND_DIR / ".env")]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=ENV_FILES,
        extra="allow"
    )

    PROJECT_NAME: str = "Demand Decision Intelligence"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"

    # Security (HS256 with 256-bit / 32+ byte key)
    SECRET_KEY: str = "b8f2a63d91e48c73d9e01f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS - Explicit origin list, no wildcards when credentials enabled (Prompt 3.3)
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://postgres:yash@localhost:5432/demand_decision_db"

    # SKU & Upload Pipeline Settings
    AUTO_CREATE_UNKNOWN_SKUS: bool = True


settings = Settings()
