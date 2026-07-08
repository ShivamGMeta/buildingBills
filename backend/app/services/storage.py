"""Storage abstraction — local filesystem in dev, object storage later."""
from pathlib import Path
from typing import Protocol

from ..config import settings


class Storage(Protocol):
    def save(self, rel_path: str, data: bytes) -> str: ...
    def load(self, rel_path: str) -> bytes | None: ...


class LocalStorage:
    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.storage_dir)

    def save(self, rel_path: str, data: bytes) -> str:
        path = self.root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return rel_path

    def load(self, rel_path: str) -> bytes | None:
        path = self.root / rel_path
        if not path.is_file():
            return None
        return path.read_bytes()


def get_storage() -> Storage:
    return LocalStorage()
