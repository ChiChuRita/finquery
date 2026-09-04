"""Get the GGUF files onto disk, with progress the UI can poll.

Three ways a file becomes ready, cheapest first: it is already in the models folder, a parked
copy elsewhere has the right size and hash and can be linked in, or it is downloaded from
Hugging Face. Progress is per file so the Settings card can show a bar for each.
"""

import hashlib
import shutil
import threading
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from finquery.local.catalog import LOCAL_MODELS, FileSpec, ModelSpec
from finquery.providers import ModelSlot

FileState = Literal["missing", "verifying", "downloading", "ready", "error"]

CHUNK = 4 * 1024 * 1024

#: Called with the number of bytes written so far.
Report = Callable[[int], None]

#: A fetcher writes `spec` to `destination`, calling `report` with the bytes written so far.
Fetch = Callable[[FileSpec, Path, Report], None]


@dataclass
class FileProgress:
    """What the Settings card shows for one file."""

    slot: ModelSlot
    model: str
    kind: str
    filename: str
    size: int
    downloaded: int
    state: FileState
    source: str | None = None
    error: str | None = None


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def http_fetch(spec: FileSpec, destination: Path, report: Report) -> None:
    """Stream one file from Hugging Face, verifying the hash before it is put in place."""
    partial = destination.with_suffix(destination.suffix + ".part")
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    written = 0
    request = urllib.request.Request(spec.url, headers={"User-Agent": "finquery"})  # noqa: S310
    with urllib.request.urlopen(request) as response, partial.open("wb") as handle:  # noqa: S310
        while block := response.read(CHUNK):
            handle.write(block)
            digest.update(block)
            written += len(block)
            report(written)
    actual = digest.hexdigest()
    if actual != spec.sha256:
        partial.unlink(missing_ok=True)
        raise ValueError(f"{spec.filename} downloaded with hash {actual}, expected {spec.sha256}")
    partial.replace(destination)


def _link_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    try:
        destination.hardlink_to(source)
    except OSError:
        # Different filesystem: a copy costs disk but keeps the parked original intact.
        shutil.copy2(source, destination)


class DownloadManager:
    """Owns the models folder: what is there, what is coming, and how far along it is."""

    def __init__(
        self,
        models_dir: Path,
        *,
        models: dict[ModelSlot, ModelSpec] | None = None,
        parked_dirs: Sequence[Path] = (),
        fetch: Fetch = http_fetch,
    ) -> None:
        self.models_dir = models_dir
        self.models = models if models is not None else LOCAL_MODELS
        self.parked_dirs = tuple(parked_dirs)
        self._fetch = fetch
        self._lock = threading.Lock()
        self._live: dict[str, FileProgress] = {}
        self._worker: threading.Thread | None = None

    def path(self, spec: ModelSpec, file: FileSpec) -> Path:
        return spec.path(self.models_dir, file)

    def progress(self) -> list[FileProgress]:
        """The state of every file: what this process did to it, else what is on disk."""
        rows: list[FileProgress] = []
        with self._lock:
            live = dict(self._live)
        for spec in self.models.values():
            for file in spec.files:
                path = self.path(spec, file)
                on_disk = path.is_file() and path.stat().st_size == file.size
                # A remembered row also carries where the file came from, which the disk cannot say.
                if (known := live.get(file.filename + spec.name)) is not None and (on_disk or known.state != "ready"):
                    rows.append(known)
                    continue
                rows.append(
                    FileProgress(
                        slot=spec.slot,
                        model=spec.name,
                        kind=file.kind,
                        filename=file.filename,
                        size=file.size,
                        downloaded=file.size if on_disk else 0,
                        state="ready" if on_disk else "missing",
                    )
                )
        return rows

    def ready(self, slot: ModelSlot) -> bool:
        spec = self.models[slot]
        return all(self.path(spec, file).is_file() for file in spec.files)

    def missing(self) -> list[tuple[ModelSpec, FileSpec]]:
        return [(spec, file) for spec in self.models.values() for file in spec.files if not self.path(spec, file).is_file()]

    def busy(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def start(self, slots: Iterable[ModelSlot] | None = None) -> None:
        """Fetch the missing files in the background. A second call while busy is a no-op."""
        if self.busy():
            return
        wanted = set(slots) if slots is not None else set(self.models)
        jobs = [(spec, file) for spec, file in self.missing() if spec.slot in wanted]
        if not jobs:
            return
        with self._lock:
            for spec, file in jobs:
                self._live[file.filename + spec.name] = FileProgress(
                    slot=spec.slot,
                    model=spec.name,
                    kind=file.kind,
                    filename=file.filename,
                    size=file.size,
                    downloaded=0,
                    state="verifying" if self._candidates(file) else "downloading",
                )
        self._worker = threading.Thread(target=self._run, args=(jobs,), name="finquery-downloads", daemon=True)
        self._worker.start()

    def ensure(self, slot: ModelSlot, *, timeout: float = 3600) -> None:
        """Block until the slot's files are on disk. Used by the lazy model loader."""
        if self.ready(slot):
            return
        self.start([slot])
        if self._worker is not None:
            self._worker.join(timeout)
        if not self.ready(slot):
            errors = [row.error for row in self.progress() if row.slot == slot and row.error]
            raise RuntimeError(
                f"the {slot} model is not on disk: " + (errors[0] if errors else "download did not finish")
            )

    def _run(self, jobs: Sequence[tuple[ModelSpec, FileSpec]]) -> None:
        for spec, file in jobs:
            key = file.filename + spec.name
            destination = self.path(spec, file)
            try:
                if (parked := self._reuse(file, destination)) is not None:
                    self._update(key, downloaded=file.size, state="ready", source=f"a parked copy at {parked}")
                    continue
                self._update(key, downloaded=0, state="downloading")
                self._fetch(file, destination, lambda done, key=key: self._update(key, downloaded=done))
                self._update(key, downloaded=file.size, state="ready", source=f"{file.repo_id} on Hugging Face")
            except Exception as exc:  # noqa: BLE001 - the state is the report; nothing above can act on it
                self._update(key, state="error", error=str(exc))

    def _candidates(self, file: FileSpec) -> list[Path]:
        """Parked files of exactly the right size, so worth hashing."""
        return [
            candidate
            for directory in self.parked_dirs
            if directory.is_dir()
            for candidate in sorted(directory.iterdir())
            if candidate.is_file() and candidate.stat().st_size == file.size
        ]

    def _reuse(self, file: FileSpec, destination: Path) -> Path | None:
        """Link in a parked copy whose hash matches, so nothing is downloaded twice."""
        for candidate in self._candidates(file):
            if sha256_of(candidate) == file.sha256:
                _link_or_copy(candidate, destination)
                return candidate
        return None

    def _update(self, key: str, **fields: object) -> None:
        with self._lock:
            row = self._live.get(key)
            if row is None:
                return
            for name, value in fields.items():
                setattr(row, name, value)
