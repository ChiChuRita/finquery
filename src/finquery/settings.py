"""Process configuration, read from the environment and the local .env file."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["openrouter", "local"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="FINQUERY_", extra="ignore")

    provider: Provider = "openrouter"
    db_path: Path = Path("data/finquery.db")
    host: str = "127.0.0.1"
    port: int = 8000
    # OpenRouter's own tooling expects this exact name, so it is read without the prefix.
    openrouter_api_key: str | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
