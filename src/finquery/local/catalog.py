"""What the local provider needs on disk: three Gemma 4 GGUFs, their projectors, two adapters.

Sizes and hashes are the Hugging Face file metadata, so a parked copy can be verified before
it is reused and a finished download can be checked.

This is the file-level catalog. The catalog the user picks from, across both providers, is
`finquery.catalog`; a local entry there carries one of the `ModelSpec` values below. All three
speak the `gemma` wire format. Qwen3.5 9B left the catalog in ticket 67, after the cluster
benchmark of 2026-09-06 placed it behind the 12B in every column; models that are benchmarked
but not offered live in `bench/finquery_bench/candidates.py`.
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
    """Which of the two seats in memory it occupies: `fast` (Gemma 4 E4B, resident, also the
    smallest chat entry) or `chat` (the 12B or the 26B, swapped in and out). See docs/adr/0013."""
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
"""The sub-agent slot and the smallest chat entry. Resident whenever the local provider is in
use, because every adapter attaches to it and because a sub-agent runs behind almost every chat
turn. A chat on this entry holds the same seat, so it is never loaded twice. See ADR 0006."""

LOCAL_GEMMA_12B = ModelSpec(
    key="local:gemma-4-12b",
    seat="chat",
    name="gemma-4-12b-it",
    label="Gemma 4 12B (local)",
    wire="gemma",
    weights=FileSpec(
        kind="weights",
        repo_id="unsloth/gemma-4-12b-it-GGUF",
        filename="gemma-4-12b-it-Q4_K_M.gguf",
        size=7121861440,
        sha256="0a270ec9fe6b34f4a0d33992b6135117b484ebc4766ab76b51d4ae8c457e4c42",
    ),
    projector=FileSpec(
        kind="projector",
        repo_id="unsloth/gemma-4-12b-it-GGUF",
        filename="mmproj-F16.gguf",
        size=175115840,
        sha256="91f086971e56d7a7d8d39e271873fccdb49541bd259d6e02c401a4f1cb7a219e",
    ),
)

LOCAL_GEMMA_26B = ModelSpec(
    key="local:gemma-4-26b",
    seat="chat",
    name="gemma-4-26B-A4B-it",
    label="Gemma 4 26B (local)",
    wire="gemma",
    # UD-Q3_K_XL rather than the Q4_K_M the other two use: 12.9 GB next to a resident E4B is
    # what a 24 GB Mac can hold, and Q4_K_M is 16.9 GB. Same family and same wire format as
    # the cloud entry, so a question can be compared on both.
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

LOCAL_CHAT_MODELS: tuple[ModelSpec, ...] = (LOCAL_GEMMA_12B, LOCAL_GEMMA_26B)
"""The two local chat models that take the chat seat, the shipped one first. Gemma 4 12B is
what a new conversation starts on since the cluster benchmark of 2026-09-06 (87 percent figure
match on the SQL set against E4B's 66, 81 against 45 on charts). The 26B A4B is the bigger
alternative, the same model the cloud entry runs. They share one seat: 12B plus E4B is about
12.9 GB and the 26B is 12.9 GB of weights on its own, so choosing one drains and unloads the
other (`LocalStack.holding`). E4B is the third local chat entry and sits in the fast seat."""

LOCAL_MODELS: dict[str, ModelSpec] = {spec.key: spec for spec in (LOCAL_FAST, *LOCAL_CHAT_MODELS)}


def adapter_path(models_dir: Path, name: AdapterName) -> Path:
    """Where the LoRA adapter for one sub-agent is expected. Missing is a supported state."""
    return models_dir / "adapters" / f"{name}.gguf"
