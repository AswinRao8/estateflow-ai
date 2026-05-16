from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class MarketConfig(BaseModel):
    """Deployment-level market parameters.

    Controls how prices, areas, timestamps, and AI response style are expressed.
    Does NOT affect workflow logic, routing, or database schema — only formatting
    and prompt construction.

    Set these fields via environment variables with the prefix MARKET__
    (e.g. MARKET__CURRENCY_CODE=AED). In V1 a single deployment serves one market.
    """
    currency_code: str = "USD"
    currency_symbol: str = "$"
    area_unit: str = "sqm"                  # "sqm" or "sqft"
    timezone: str = "UTC"                    # IANA timezone string
    communication_locale: str = "en"         # BCP 47 language tag — influences AI tone
    # Optional display-name overrides for PropertyType enum values.
    # Example: {"APARTMENT": "flat", "HOUSE": "terraced house"}
    property_terminology: dict[str, str] = {}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "EstateFlow AI"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    # API
    api_prefix: str = "/api/v1"

    # Logging
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/estateflow"

    # Security
    secret_key: str = "change-this-before-production"

    # WhatsApp Cloud API (Phase 2)
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_webhook_verify_token: str = "estateflow-verify"
    whatsapp_webhook_secret: str = ""
    whatsapp_api_version: str = "v18.0"

    # Tenant (V1 single-tenant — all inbound messages map to this tenant)
    default_tenant_id: str = "default"

    # Market configuration — deployment-level, not per-request
    market: MarketConfig = MarketConfig()

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"


@lru_cache
def get_settings() -> Settings:
    return Settings()
