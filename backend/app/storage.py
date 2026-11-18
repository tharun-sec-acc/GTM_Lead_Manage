"""Storage adapter interface and local Docker-volume implementation."""

import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path


class StorageError(Exception):
    pass


class StorageKeyNotFound(StorageError):
    pass


class StorageQuotaExceeded(StorageError):
    pass


class StorageAdapter(ABC):
    @abstractmethod
    def store(self, key: str, data: bytes) -> str:
        """Persist data and return the storage key."""

    @abstractmethod
    def retrieve(self, key: str) -> bytes:
        """Return data for key; raise StorageKeyNotFound if missing."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete data for key; succeed silently if already absent."""


class LocalStorageAdapter(StorageAdapter):
    """Stores files on the local filesystem under base_dir."""

    def __init__(self, base_dir: str | None = None):
        if base_dir is None:
            base_dir = os.environ.get("ATTACHMENT_STORAGE_DIR", "/app/attachments")
            try:
                Path(base_dir).mkdir(parents=True, exist_ok=True)
            except (PermissionError, OSError):
                base_dir = str(Path(__file__).resolve().parent.parent / "attachments")
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Sanitise key: allow only alphanumeric, dash, underscore, dot
        safe = "".join(c for c in key if c.isalnum() or c in "-_.")
        if not safe:
            raise StorageError(f"Invalid storage key: {key!r}")
        return self._base / safe

    def store(self, key: str, data: bytes) -> str:
        path = self._path(key)
        try:
            # Atomic write via temp file in the same directory
            fd, tmp = tempfile.mkstemp(dir=self._base)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                os.replace(tmp, path)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except OSError as exc:
            if exc.errno == 28:  # ENOSPC
                raise StorageQuotaExceeded("Attachment storage is full.") from exc
            raise StorageError(f"Failed to write attachment: {exc}") from exc
        return key

    def retrieve(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise StorageKeyNotFound(f"Attachment key {key!r} not found.")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        try:
            path.unlink()
        except FileNotFoundError:
            pass  # idempotent
        except OSError as exc:
            raise StorageError(f"Failed to delete attachment: {exc}") from exc


# Singleton default adapter — override in tests
_default_adapter: StorageAdapter | None = None


def get_storage() -> StorageAdapter:
    global _default_adapter
    if _default_adapter is None:
        _default_adapter = LocalStorageAdapter()
    return _default_adapter


def set_storage(adapter: StorageAdapter) -> None:
    global _default_adapter
    _default_adapter = adapter