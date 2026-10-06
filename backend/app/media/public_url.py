"""
Public URL for a version's image, as Buffer must fetch it.

Buffer has no upload endpoint: it fetches the image from a public HTTPS URL when the
post goes out. A version with a ready image but no usable public base URL must not be
published as text-only. That would be a silent fallback, so it fails loudly.
"""
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.media.models import MediaAsset, MediaAssetStatus, MediaAssetType
from app.publishing.interface import PermanentPublishingError


def public_image_url_for_version(db: Session, content_version_id: UUID) -> str | None:
    """Returns the public URL of the newest ready image, None if the version has none."""
    asset = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.content_version_id == content_version_id,
            MediaAsset.type == MediaAssetType.IMAGE,
            MediaAsset.status == MediaAssetStatus.READY,
        )
        .order_by(MediaAsset.created_at.desc())
        .first()
    )
    if asset is None:
        return None

    if asset.storage_url.startswith("https://"):
        return asset.storage_url  # already a public Supabase URL
    base = (settings.media_public_base_url or "").strip().rstrip("/")
    if not base.startswith("https://"):
        raise PermanentPublishingError(
            "This version has an image, but MEDIA_PUBLIC_BASE_URL is not set to a public "
            "https:// address. Buffer must fetch the image from a public URL, so the post "
            "was not sent. Set MEDIA_PUBLIC_BASE_URL, or remove the image."
        )
    return base + asset.storage_url


def buffer_assets_for(image_url: str | None) -> list[dict]:
    """Buffer CreatePostInput.assets for one image."""
    return [{"image": {"url": image_url}}] if image_url else []
