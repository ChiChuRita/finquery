"""What the local provider needs on disk: two Gemma 4 GGUFs, their projectors, two adapters.

Sizes and hashes are the Hugging Face file metadata, so a parked copy can be verified before
it is reused and a finished download can be checked.

This is the file-level catalog. The catalog the user picks from, across both providers, is
`finquery.catalog`; a local entry there carries one of the `ModelSpec` values below. Both
speak the `gemma` wire format. Qwen3.5 9B left the catalog in ticket 67 and Gemma 4 12B in
ticket 73, where the 26B A4B took the chat seat; models that are benchmarked but not offered
live in `bench/finquery_bench/candidates.py`, which is where the 12B spec went, key and all.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from finquery.local.wire import WireName
from finquery.providers import ModelRole

FileKind = Literal["weights", "projector"]

AdapterName = Literal["query", "chart"]
ADAPTER_NAMES: tuple[AdapterName, ...] = ("query", "chart")

HUGGING_FACE = "https://huggingface.co"


@dataclass(frozen=True)
class FileSpec:
    """One file to have on disk, identified well enough to verify a copy of it."""

    kind: FileKind
    repo_id: str
    filename: str
    size: int
    sha256: str

    @property
    def url(self) -> str:
        return f"{HUGGING_FACE}/{self.repo_id}/resolve/main/{self.filename}"


@dataclass(frozen=True)
class ModelSpec:
    """One concrete GGUF the local provider can load."""

    key: str
    """The catalog key this model is offered under (`finquery.catalog`)."""
    seat: ModelRole
    """Which role this model is the local answer to: `fast` (Gemma 4 E4B, what a sub-agent role
    set to `fast` runs on and where the adapters attach) or `chat`. Not a place in memory: one
    model is loaded at a time, whatever its seat. See docs/adr/0013 and its ticket 68
    amendment."""
    name: str
    label: str
    """How the UI names this model: the selector, the turn chips, the models card."""
    wire: WireName
    """Which chat wire format this model speaks (`finquery.local.wire`)."""
    weights: FileSpec
    projector: FileSpec

    @property
    def files(self) -> tuple[FileSpec, ...]:
        return (self.weights, self.projector)

    def directory(self, models_dir: Path) -> Path:
        return models_dir / self.name

    def path(self, models_dir: Path, spec: FileSpec) -> Path:
        return self.directory(models_dir) / spec.filename


LOCAL_FAST = ModelSpec(
    key="local:gemma-4-e4b",
    seat="fast",
    name="gemma-4-E4B-it",
    label="Gemma 4 E4B (local)",
    wire="gemma",
    weights=FileSpec(
        kind="weights",
        repo_id="unsloth/gemma-4-E4B-it-GGUF",
        filename="gemma-4-E4B-it-Q4_K_M.gguf",
        size=4977171584,
        sha256="85a896a047553e842f25297ee5b031d64ff30147d9c4af17b1e4b394cd1fab87",
    ),
    projector=FileSpec(
        kind="projector",
        repo_id="unsloth/gemma-4-E4B-it-GGUF",
        filename="mmproj-F16.gguf",
        size=990372672,
        sha256="ddf46c21d7078e95338cfc22306b19b276a29a5ad089023449dd54d4b6170a51",
    ),
)
"""The sub-agent slot and the smallest chat entry. What a role set to `fast` runs on and what
the adapters are trained for, so a chat on this entry runs the fine-tuned sub-agents with no
swap: the same model answers the chat and every sub-agent behind it. See ADR 0006."""

LOCAL_GEMMA_26B = ModelSpec(
    key="local:gemma-4-26b",
    seat="chat",
    name="gemma-4-26B-A4B-it",
    label="Gemma 4 26B (local)",
    wire="gemma",
    # UD-Q3_K_XL rather than the Q4_K_M the other two use: 12.9 GB is what a 24 GB Mac can
    # decode at 32k context, and Q4_K_M is 16.9 GB. Same family and same wire format as the
    # cloud entry, so a question can be compared on both.
    # TODO: one quant for every machine; Q4_K_M (sha f2c28b3d...) once a 32 GB machine matters.
    weights=FileSpec(
        kind="weights",
        repo_id="unsloth/gemma-4-26B-A4B-it-GGUF",
        filename="gemma-4-26B-A4B-it-UD-Q3_K_XL.gguf",
        size=12907280096,
        sha256="90a918830420e6a36e01c0d219e563f1d0ca7f223dffd90ad4e02ef4f3253fde",
    ),
    projector=FileSpec(
        kind="projector",
        repo_id="unsloth/gemma-4-26B-A4B-it-GGUF",
        filename="mmproj-F16.gguf",
        size=1193058784,
        sha256="418a6d8723067cd712235facbbc5cba6c8fbbd413fc1292d2aace5a027d5a42f",
    ),
)

LOCAL_CHAT_MODELS: tuple[ModelSpec, ...] = (LOCAL_GEMMA_26B,)
"""The local chat models with a seat of `chat`. Gemma 4 26B A4B is what a new conversation
starts on since ticket 73: it ties the 12B it replaced on the SQL set (79 against 78 percent of
459 questions) and it is much faster on the laptop, 38.1 tok/s generation against 22.3 and
480 tok/s prompt processing against 205 (`bench/results/20260907-local-tokens-per-second.md`).
It is also the same model the cloud entry runs, so a question can be compared on the two. One
model is loaded at a time (ticket 68), so choosing another one drains and unloads the one in
memory first (`LocalStack.holding`); E4B is the other local chat entry and the one every `fast`
role means."""

LOCAL_MODELS: dict[str, ModelSpec] = {spec.key: spec for spec in (LOCAL_FAST, *LOCAL_CHAT_MODELS)}


def adapter_path(models_dir: Path, name: AdapterName) -> Path:
    """Where the LoRA adapter for one sub-agent is expected. Missing is a supported state."""
    return models_dir / "adapters" / f"{name}.gguf"
