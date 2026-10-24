"""Central configuration, loaded from environment variables or a local `.env` file."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="FA_", extra="ignore")

    data_dir: Path = Path("data")
    export_dir: Path = Path("data/raw")  # an extracted Google Takeout export
    timezone: str = "UTC"
    # Browser origins allowed to call the API (the Expo web build). Native apps do not need CORS.
    cors_origins: list[str] = ["http://localhost:8081"]
    # Google Health API: an OAuth client of type "Desktop app" and where its refresh token is kept.
    google_client_id: SecretStr | None = None
    google_client_secret: SecretStr | None = None
    google_token_file: Path = Path("data/google_token.json")
    # Connecting Google Health from the app: the key that encrypts stored tokens (Fernet), this
    # server's address for Google's callback, and the app's address to send the browser back to.
    token_key: SecretStr | None = None
    public_url: str = "http://127.0.0.1:8000"
    app_url: str = "http://localhost:8081"
    # Opt-in only after the confirmed-action path and Google write scopes are configured.
    google_writes_enabled: bool = False
    # The database: Postgres from docker-compose.yml locally, a managed Postgres when deployed.
    database_url: str = (
        "postgresql+psycopg://fitbit_agent:local-dev-only@localhost:5433/fitbit_agent"
    )
    # The agent's language model: a small model for tool loops, a large one for write-ups.
    openai_api_key: SecretStr | None = None
    openai_small_model: str = "gpt-5.4-mini"
    openai_large_model: str = "gpt-5.5"
    # The router: TypeSafe's Jev, given the question text only.
    typesafe_api_key: SecretStr | None = None
    typesafe_model: str = "jev-latest"
    typesafe_base_url: str = "https://api.typesafe.ai"
    # Accounts: who may approve sign-ups, and how long a device stays signed in.
    admin_emails: list[str] = []
    session_days: int = 30
    # Questions from the app: daily spending caps (US dollars, from stored answer costs, per local
    # day) and how long a request waits for the answer before telling the app to check back.
    chat_daily_cap_per_user_usd: float = 0.10
    chat_daily_cap_total_usd: float = 0.50
    chat_wait_s: float = 55.0
    # Hard cap on model spending by this process, in US dollars.
    llm_spend_cap_usd: float = 20.0


settings = Settings()
