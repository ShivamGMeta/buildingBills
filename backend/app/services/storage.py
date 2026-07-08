"""Storage abstraction — local filesystem today; a GoogleDriveStorage (or
object storage) can be added behind the same interface without touching any
endpoint. Select via settings.storage_backend. Files are ALWAYS streamed
through the API's scoped endpoints — storage URLs/links are never exposed."""
import mimetypes
from pathlib import Path
from typing import Protocol

from ..config import settings


class Storage(Protocol):
    def save(self, rel_path: str, data: bytes,
             content_type: str = "application/octet-stream") -> str: ...
    def load(self, rel_path: str) -> bytes | None: ...
    def delete(self, rel_path: str) -> None: ...
    def content_type_of(self, rel_path: str) -> str | None: ...


class LocalStorage:
    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.storage_dir)

    def _path(self, rel_path: str) -> Path:
        path = (self.root / rel_path).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError("Path escapes storage root")
        return path

    def save(self, rel_path: str, data: bytes,
             content_type: str = "application/octet-stream") -> str:
        path = self._path(rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return rel_path

    def load(self, rel_path: str) -> bytes | None:
        path = self._path(rel_path)
        if not path.is_file():
            return None
        return path.read_bytes()

    def delete(self, rel_path: str) -> None:
        path = self._path(rel_path)
        path.unlink(missing_ok=True)

    def content_type_of(self, rel_path: str) -> str | None:
        # Local backend infers from the extension; callers that need the
        # exact uploaded type should keep it in their own metadata row
        # (ReadingPhoto.content_type does).
        guessed, _ = mimetypes.guess_type(rel_path)
        return guessed


def get_storage() -> Storage:
    # "gdrive" (owner-account OAuth so files count against the personal
    # 2 TB plan) is a planned additive backend — see docs/02-gap-analysis.md
    # §2.2. Records always stay in the database; only blobs go to storage.
    if settings.storage_backend != "local":
        raise NotImplementedError(
            f"Storage backend '{settings.storage_backend}' not implemented yet")
    return LocalStorage()
