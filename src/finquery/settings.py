"""Process configuration, read from the environment and the local .env file."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["openrouter", "local"]


def _a_model_a_role_can_run_on(value: str) -> str:
    """A sub-agent role setting is one of the two model roles or a catalog key.

    Checked here so a typo in `.env` is a startup error naming the variable, not a 503 the
    first time that one sub-agent runs.
    """
    if value in ("chat", "fast") or value.startswith(("local:", "openrouter:")):
        return value
    raise ValueError("expected `chat`, `fast` or a catalog key such as local:gemma-4-12b")


SubagentModel = Annotated[str, AfterValidator(_a_model_a_role_can_run_on)]


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
    """Context cap for the loaded local model, and the size a swapped-in one is loaded at.

    One model is loaded at a time (ADR 0013, ticket 68 amendment), so 32k with flash attention
    and a q8_0 KV cache fits every catalog model inside the Metal working set of a 24 GB Mac,
    the 12.9 GB 26B included. Lower it on a smaller machine. See
    docs/adr/0006-local-gemma-4-through-llama-cpp.md."""
    # OpenRouter's own tooling expects this exact name, so it is read without the prefix.
    openrouter_api_key: str | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
    """The key the cloud entry answers with. From the environment or `.env` at startup; the
    Settings models card can set or clear it while the app runs (`Catalog.set_openrouter_key`),
    which also writes it to `key_file` for the next start."""
    key_file: Path = Path(".env")
    """Where a key entered in Settings is kept (FINQUERY_KEY_FILE): the `.env` this process
    reads at startup, so the same line serves both. Only the `OPENROUTER_API_KEY` line is
    touched."""
    extraction_page_concurrency: int | None = None
    """How many statement pages the extraction sub-agent reads at once. Unset means 4 on the
    local provider (one model, serialized anyway) and 12 on a hosted one, where the pages really
    do run in parallel (FINQUERY_EXTRACTION_PAGE_CONCURRENCY)."""
    openrouter_fast_model: str = "google/gemma-4-26b-a4b-it"
    """The hosted sub-agent slot: what a sub-agent role set to `fast` runs on when the chat is
    on a cloud entry (FINQUERY_OPENROUTER_FAST_MODEL). Its local counterpart is Gemma 4 E4B.
    The hosted chat entry is not a setting: it is the catalog's own id
    (`finquery.catalog.HOSTED_CHAT_MODELS`), so it is listed even when this slot points at it,
    which is what development on one hosted model does."""

    # One setting per sub-agent role (FINQUERY_SUBAGENT_MODEL_<ROLE>). Each takes `chat` (the
    # conversation's own entry, the default), `fast` (its provider's sub-agent slot) or a
    # catalog key that pins the role to one model. See finquery.catalog.Catalog.for_role.
    subagent_model_query: SubagentModel = "chat"
    subagent_model_chart: SubagentModel = "chat"
    subagent_model_categorizer: SubagentModel = "chat"
    subagent_model_extraction: SubagentModel = "chat"
    subagent_model_memory: SubagentModel = "chat"
    subagent_model_summary: SubagentModel = "chat"
    subagent_model_weblookup: SubagentModel = "chat"

    def subagent_model(self, role: str) -> str:
        """What one sub-agent role is set to. See `finquery.providers.SUBAGENT_ROLES`."""
        return str(getattr(self, f"subagent_model_{role}"))


KEY_LINE = "OPENROUTER_API_KEY"


def save_openrouter_key(path: Path, key: str | None) -> None:
    """Write the key the Settings page took into the env file, replacing the existing line.

    Every other line is kept byte for byte, so a hand-edited `.env` keeps its comments and its
    order. Clearing writes an empty value rather than dropping the line, so the file still
    documents where the key goes. A file that does not exist yet is created with the one line.
    """
    lines = path.read_text().splitlines() if path.is_file() else []
    fresh = f"{KEY_LINE}={key or ''}"
    kept = [line for line in lines if not line.startswith(f"{KEY_LINE}=")]
    at = next((i for i, line in enumerate(lines) if line.startswith(f"{KEY_LINE}=")), len(kept))
    kept.insert(at, fresh)
    path.write_text("\n".join(kept) + "\n")


def page_concurrency(settings: Settings) -> int:
    """Pages in flight for PDF extraction: the setting, else 12 hosted, 4 local."""
    if settings.extraction_page_concurrency is not None:
        return max(1, settings.extraction_page_concurrency)
    return 4 if settings.provider == "local" else 12
