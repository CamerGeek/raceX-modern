from functools import lru_cache

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
    chariow_return_url: str = "http://localhost:3000/account?payment=complete"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
