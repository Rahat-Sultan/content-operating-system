from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO


class MediaStorageError(Exception):
    """Base exception for media storage errors."""
    pass


@dataclass
class StoredMediaResult:
    storage_url: str
    file_path: str
    size_bytes: int


class MediaStorage(ABC):
    """
    Abstract storage boundary for media assets.
    Keeps binaries out of PostgreSQL and Git.
    """

    @abstractmethod
    def save(
        self,
        filename: str,
        data: bytes,
        mime_type: str = "image/png",
    ) -> StoredMediaResult:
        """Saves media bytes and returns a durable storage reference / URL."""
        pass

    @abstractmethod
    def get_path(self, storage_url: str) -> str | None:
        """Returns the local filesystem path for a storage URL if locally managed."""
        pass

    @abstractmethod
    def delete(self, storage_url: str) -> bool:
        """Deletes media by its storage URL."""
        pass
