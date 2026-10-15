"""Central configuration, loaded from environment variables or a local `.env` file."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="FA_", extra="ignore")

    data_dir: Path = Path("data")
    timezone: str = "UTC"


settings = Settings()
