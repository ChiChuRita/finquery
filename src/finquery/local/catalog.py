"""What the local provider needs on disk: two GGUF models, their projectors, two adapters.

Sizes and hashes are the Hugging Face file metadata, so a parked copy can be verified before
it is reused and a finished download can be checked.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from finquery.providers import MODEL_SLOTS, ModelSlot

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
    """The concrete model behind one logical slot."""

    slot: ModelSlot
    name: str
    weights: FileSpec
    projector: FileSpec

    @property
    def files(self) -> tuple[FileSpec, ...]:
        return (self.weights, self.projector)

    def directory(self, models_dir: Path) -> Path:
        return models_dir / self.name

    def path(self, models_dir: Path, spec: FileSpec) -> Path:
        return self.directory(models_dir) / spec.filename


LOCAL_MODELS: dict[ModelSlot, ModelSpec] = {
    "fast": ModelSpec(
        slot="fast",
        name="gemma-4-E4B-it",
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
    ),
    "quality": ModelSpec(
        slot="quality",
        name="gemma-4-12b-it",
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
    ),
}

assert set(LOCAL_MODELS) == set(MODEL_SLOTS)


def adapter_path(models_dir: Path, name: AdapterName) -> Path:
    """Where the LoRA adapter for one sub-agent is expected. Missing is a supported state."""
    return models_dir / "adapters" / f"{name}.gguf"
