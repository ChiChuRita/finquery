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

    context_budget: int = 32768
    """Tokens one turn may fill, summary and recent turns together.

    A cap, not a raise: the OpenRouter models hold 262k, which no personal-finance conversation
    reaches, so the budget is capped here to keep prompts small and compression demonstrable.
    On the local provider `local_n_ctx` caps it further. Compression starts at 60 percent of
    this. See finquery.context."""

    # Local provider (FINQUERY_PROVIDER=local).
    models_dir: Path = Path("models")
    parked_models_dir: Path | None = None
    """A folder of already-downloaded GGUF files. A copy whose hash matches is linked in
    instead of downloaded again."""
    local_n_ctx: int = 16384
    """Context cap per resident model.

    16k is the largest that keeps both Gemma 4 models resident inside the 18.2 GB Metal
    working set of a 24 GB Mac, with flash attention and a q8_0 KV cache. Raise it on a
    machine with more memory. See docs/adr/0006-local-gemma-4-through-llama-cpp.md."""
    # OpenRouter's own tooling expects this exact name, so it is read without the prefix.
    openrouter_api_key: str | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
