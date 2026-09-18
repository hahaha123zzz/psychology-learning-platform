from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "Psychology Learning Platform"
    log_level: str = "INFO"
    database_url: str = Field(
        default="postgresql+asyncpg://psychology:change-me@127.0.0.1:5432/psychology_learning"
    )
    redis_url: str = "redis://127.0.0.1:6379/0"
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "change-me"
    minio_secret_key: str = "change-me"
    minio_secure: bool = False
    minio_bucket: str = "course-materials"


@lru_cache
def get_settings() -> Settings:
    return Settings()

