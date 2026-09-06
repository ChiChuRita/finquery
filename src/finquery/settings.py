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
    local_n_ctx: int = 32768
    """Context cap per resident model, and the size a swapped-in chat model is reloaded at.

    32k is what Gemma 4 E4B and Qwen3.5 9B take together: 13.5 GB inside the 18.2 GB Metal
    working set of a 24 GB Mac, with flash attention and a q8_0 KV cache. Lower it on a
    smaller machine. See docs/adr/0006-local-gemma-4-through-llama-cpp.md."""
    # OpenRouter's own tooling expects this exact name, so it is read without the prefix.
    openrouter_api_key: str | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
    extraction_page_concurrency: int | None = None
    """How many statement pages the extraction sub-agent reads at once. Unset means 4 on the
    local provider (one model, serialized anyway) and 12 on a hosted one, where the pages really
    do run in parallel (FINQUERY_EXTRACTION_PAGE_CONCURRENCY)."""
    openrouter_fast_model: str = "google/gemma-4-26b-a4b-it"
    """The hosted sub-agent slot: what every sub-agent of a cloud chat entry runs on
    (FINQUERY_OPENROUTER_FAST_MODEL). Its local counterpart is Gemma 4 E4B."""
    openrouter_quality_model: str = "qwen/qwen3.5-9b"
    openrouter_second_chat_model: str = "google/gemma-4-26b-a4b-it"
    """The two hosted chat entries of the catalog, in the order the picker lists them
    (FINQUERY_OPENROUTER_QUALITY_MODEL, FINQUERY_OPENROUTER_SECOND_CHAT_MODEL). The defaults are
    Qwen3.5 9B, the model class the local provider ships, and the closest hosted Gemma 4 there
    is: OpenRouter has no Gemma 4 12B. Any OpenRouter id works here to try another model without
    a code change. See docs/adr/0012-model-catalog-across-providers.md."""


def page_concurrency(settings: Settings) -> int:
    """Pages in flight for PDF extraction: the setting, else 12 hosted, 4 local."""
    if settings.extraction_page_concurrency is not None:
        return max(1, settings.extraction_page_concurrency)
    return 4 if settings.provider == "local" else 12
