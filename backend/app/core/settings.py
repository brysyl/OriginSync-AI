from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str | None = None
    supabase_url: str | None = None
    supabase_anon_key: SecretStr | None = None
    supabase_service_role_key: SecretStr | None = None
    allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    vertex_project_id: str | None = None
    vertex_location: str = "us-central1"
    vertex_model: str = "gemini-1.5-flash"
    vertex_service_account_json: SecretStr | None = None
    vertex_embedding_model: str = "text-embedding-004"

    paypal_client_id: SecretStr | None = None
    paypal_client_secret: SecretStr | None = None
    paypal_environment: Literal["sandbox", "live"] = "sandbox"
    paypal_webhook_hmac_secret: SecretStr | None = None
    n8n_webhook_hmac_secret: SecretStr | None = None
    webhook_max_clock_skew_seconds: int = Field(default=300, ge=30, le=900)

    settlement_threshold: float = Field(default=0.85, ge=0, le=1)
    max_document_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=25 * 1024 * 1024)
    classification_cache_similarity: float = Field(default=0.97, ge=0, le=1)

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    def validate_runtime_configuration(self) -> None:
        def is_configured(value: object) -> bool:
            if isinstance(value, SecretStr):
                return bool(value.get_secret_value().strip())
            if isinstance(value, str):
                return bool(value.strip())
            return bool(value)

        missing = [
            name
            for name, value in (
                ("DATABASE_URL", self.database_url),
                ("VERTEX_PROJECT_ID", self.vertex_project_id),
                ("PAYPAL_WEBHOOK_HMAC_SECRET", self.paypal_webhook_hmac_secret),
                ("N8N_WEBHOOK_HMAC_SECRET", self.n8n_webhook_hmac_secret),
            )
            if not is_configured(value)
        ]
        if missing:
            raise ValueError(f"Missing required runtime configuration: {', '.join(missing)}")
        if self.environment == "production":
            production_missing = [
                name
                for name, value in (
                    ("VERTEX_SERVICE_ACCOUNT_JSON", self.vertex_service_account_json),
                    ("PAYPAL_CLIENT_ID", self.paypal_client_id),
                    ("PAYPAL_CLIENT_SECRET", self.paypal_client_secret),
                    ("ALLOWED_ORIGINS", self.allowed_origins),
                )
                if not is_configured(value)
            ]
            if production_missing:
                raise ValueError(
                    "Missing required production configuration: " + ", ".join(production_missing)
                )


@lru_cache
def get_settings() -> Settings:
    return Settings()
