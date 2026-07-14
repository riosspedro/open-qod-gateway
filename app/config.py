from functools import lru_cache

from pydantic import (
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    database_path: str = "data/open-qod-gateway.db"
    session_cleanup_interval_seconds: float = Field(
        default=5.0,
        gt=0,
    )

    gateway_oauth_client_id: str = Field(
        default="open-qod-client",
        min_length=1,
    )
    gateway_oauth_client_secret: SecretStr
    gateway_oauth_signing_secret: SecretStr
    gateway_oauth_token_ttl_seconds: int = Field(
        default=3600,
        ge=60,
    )

    nef_base_url: str = "https://10.100.200.14:8000"
    nef_client_id: str = Field(min_length=1)
    nef_client_secret: str = Field(min_length=1)
    nef_verify_tls: bool = False
    nef_ca_bundle: str | None = None
    nef_client_cert: str | None = None
    nef_client_key: str | None = None
    nef_timeout_seconds: float = Field(default=10.0, gt=0)
    nef_scs_as_id: str = "open-qod-gateway"
    nef_notification_destination: str

    @field_validator(
        "nef_ca_bundle",
        "nef_client_cert",
        "nef_client_key",
        mode="before",
    )
    @classmethod
    def empty_tls_path_to_none(
        cls,
        value: object,
    ) -> object:
        if isinstance(value, str) and not value.strip():
            return None

        return value

    @model_validator(mode="after")
    def validate_nef_client_certificate_pair(self) -> "Settings":
        certificate_configured = self.nef_client_cert is not None
        key_configured = self.nef_client_key is not None

        if certificate_configured != key_configured:
            raise ValueError(
                "NEF_CLIENT_CERT e NEF_CLIENT_KEY devem ser "
                "configurados em conjunto."
            )

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
