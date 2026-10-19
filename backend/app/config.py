"""Central configuration, loaded from environment variables or a local `.env` file."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="FA_", extra="ignore")

    data_dir: Path = Path("data")
    export_dir: Path = Path("data/raw")  # an extracted Google Takeout export
    timezone: str = "UTC"
    # Browser origins allowed to call the API (the Expo web build). Native apps do not need CORS.
    cors_origins: list[str] = ["http://localhost:8081"]


settings = Settings()
