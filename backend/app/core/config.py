from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RaceX API"
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000"
    source_timeout_seconds: int = 20
    model_version: str = "initial-migration"
    supabase_url: str = ""
    supabase_key: str = ""
    chariow_api_key: str = ""
    chariow_pulse_secret: str = ""
    chariow_product_id: str = "prd_0hfy60zq"
    chariow_weekly_product_id: str = "prd_czkpuc2g"
    chariow_annual_product_id: str = "prd_4f2ld5qj"
    chariow_return_url: str = "http://localhost:3000/account?payment=complete"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    @model_validator(mode="after")
    def validate_chariow_product_ids(self) -> "Settings":
        product_ids = [
            self.chariow_product_id.strip(),
            self.chariow_weekly_product_id.strip(),
            self.chariow_annual_product_id.strip(),
        ]
        if any(not product_id for product_id in product_ids):
            raise ValueError("Chariow product IDs must not be empty")
        if len(set(product_ids)) != len(product_ids):
            raise ValueError("Each Chariow subscription plan must use a unique product ID")
        return self

    @property
    def chariow_plan_product_ids(self) -> dict[str, str]:
        return {
            "weekly": self.chariow_weekly_product_id.strip(),
            "monthly": self.chariow_product_id.strip(),
            "annual": self.chariow_annual_product_id.strip(),
        }

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
