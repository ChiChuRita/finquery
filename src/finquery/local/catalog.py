"""What the local provider needs on disk: two GGUF models, their projectors, two adapters.

Sizes and hashes are the Hugging Face file metadata, so a parked copy can be verified before
it is reused and a finished download can be checked.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from finquery.local.wire import WireName
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


LOCAL_MODELS: dict[ModelSlot, ModelSpec] = {
    "fast": ModelSpec(
        slot="fast",
        name="gemma-4-E4B-it",
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
    ),
    "quality": ModelSpec(
        slot="quality",
        name="Qwen3.5-9B",
        wire="qwen",
        weights=FileSpec(
            kind="weights",
            repo_id="unsloth/Qwen3.5-9B-GGUF",
            filename="Qwen3.5-9B-Q4_K_M.gguf",
            size=5680522464,
            sha256="03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8",
        ),
        projector=FileSpec(
            kind="projector",
            repo_id="unsloth/Qwen3.5-9B-GGUF",
            filename="mmproj-F16.gguf",
            size=918166080,
            sha256="f70dc3509053962b0d0d3ee8a7eacebf5d60aa560cad78254ae8698516ae029f",
        ),
    ),
}

assert set(LOCAL_MODELS) == set(MODEL_SLOTS)


def adapter_path(models_dir: Path, name: AdapterName) -> Path:
    """Where the LoRA adapter for one sub-agent is expected. Missing is a supported state."""
    return models_dir / "adapters" / f"{name}.gguf"
