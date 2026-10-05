from uuid import UUID
from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.media.schemas import GenerateMediaRequest, MediaAssetResponse
from app.media.service import generate_media_for_content_version, get_media_assets_for_content_version
from app.media.factory import get_media_storage

router = APIRouter(prefix="", tags=["media"])


@router.post(
    "/content/{content_id}/versions/{version_id}/media",
    response_model=MediaAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_media_asset(
    content_id: UUID,
    version_id: UUID,
    request: GenerateMediaRequest = GenerateMediaRequest(),
    db: Session = Depends(get_db),
):
    """
    Generate an image for a specific ContentVersion through the provider boundary.
    Persists asset safely to storage and records MediaAsset in the database.
    """
    return generate_media_for_content_version(
        db=db,
        content_id=content_id,
        version_id=version_id,
        user_prompt=request.prompt,
        regenerate=request.regenerate,
    )


@router.get(
    "/content/{content_id}/versions/{version_id}/media",
    response_model=list[MediaAssetResponse],
)
def list_media_assets(
    content_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
):
    """
    List media assets attached to a specific ContentVersion.
    """
    return get_media_assets_for_content_version(
        db=db,
        content_id=content_id,
        version_id=version_id,
    )


@router.get("/media/files/{filename}")
def serve_media_file(filename: str):
    """
    Serve locally stored media assets.
    """
    storage = get_media_storage()
    url = f"/api/media/files/{filename}"
    file_path = storage.get_path(url)
    if not file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(file_path, media_type="image/png")
