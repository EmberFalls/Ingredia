from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    app_name: str = "Ingredient Intelligence API"
    app_env: str = "development"
    database_url: str = "sqlite:///./ingredient_intelligence.db"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173"
    scoring_version: str = "1.0.0"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
