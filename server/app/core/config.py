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
    default_organization_id: str = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    database_url: str = Field(
        default="postgresql+asyncpg://psychology:change-me@127.0.0.1:5432/psychology_learning"
    )
    redis_url: str = "redis://127.0.0.1:6379/0"
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "change-me"
    minio_secret_key: str = "change-me"
    minio_secure: bool = False
    minio_bucket: str = "course-materials"

    jwt_secret: str = "dev-only-change-me-32-bytes-minimum-key!"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    login_fail_limit: int = 5
    login_fail_window_seconds: int = 900

    upload_max_mb: int = 200
    course_storage_quota_gb: int = 20
    parse_simulate_seconds: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()

