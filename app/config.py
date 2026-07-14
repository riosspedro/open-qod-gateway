from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    database_path: str = "data/open-qod-gateway.db"
    session_cleanup_interval_seconds: float = Field(
        default=5.0,
        gt=0,
    )

    nef_base_url: str = "https://10.100.200.14:8000"
    nef_client_id: str = Field(min_length=1)
    nef_client_secret: str = Field(min_length=1)
    nef_verify_tls: bool = False
    nef_timeout_seconds: float = Field(default=10.0, gt=0)
    nef_scs_as_id: str = "open-qod-gateway"
    nef_notification_destination: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
