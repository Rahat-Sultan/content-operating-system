import os
from pathlib import Path
from uuid import uuid4

from app.media.storage import MediaStorage, StoredMediaResult, MediaStorageError


class LocalFileMediaStorage(MediaStorage):
    """
    Local filesystem storage provider for media assets.
    Saves assets to a dedicated, Git-ignored directory and serves via static URL.
    """

    def __init__(self, base_dir: str | Path | None = None, url_prefix: str = "/api/media/files"):
        if base_dir is None:
            # Default to backend/media_storage
            backend_root = Path(__file__).resolve().parent.parent.parent
            base_dir = backend_root / "media_storage"
        self.base_dir = Path(base_dir)
        self.url_prefix = url_prefix.rstrip("/")
        self._ensure_dir()

    def _ensure_dir(self):
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise MediaStorageError(f"Failed to initialize media storage directory: {e}") from e

    def save(
        self,
        filename: str,
        data: bytes,
        mime_type: str = "image/png",
    ) -> StoredMediaResult:
        self._ensure_dir()
        # Sanitize filename / ensure uniqueness
        safe_name = os.path.basename(filename)
        unique_name = f"{uuid4().hex}_{safe_name}"
        target_path = self.base_dir / unique_name

        try:
            with open(target_path, "wb") as f:
                f.write(data)
        except Exception as e:
            raise MediaStorageError(f"Failed to save media file to {target_path}: {e}") from e

        storage_url = f"{self.url_prefix}/{unique_name}"
        return StoredMediaResult(
            storage_url=storage_url,
            file_path=str(target_path),
            size_bytes=len(data),
        )

    def get_path(self, storage_url: str) -> str | None:
        if not storage_url.startswith(self.url_prefix):
            return None
        rel_name = os.path.basename(storage_url)
        full_path = self.base_dir / rel_name
        if full_path.exists():
            return str(full_path)
        return None

    def delete(self, storage_url: str) -> bool:
        path = self.get_path(storage_url)
        if path and os.path.exists(path):
            try:
                os.remove(path)
                return True
            except OSError:
                return False
        return False
