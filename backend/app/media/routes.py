from uuid import UUID
from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.media.schemas import GenerateMediaRequest, MediaAssetResponse
from app.media.service import generate_media_for_content_version, get_media_assets_for_content_version
from app.media.factory import get_media_storage

from app.accounts.models import User
from app.accounts.service import current_user

router = APIRouter(prefix="", tags=["media"])


def require_owned_version(db: Session, content_id: UUID, version_id: UUID, owner_id) -> None:
    """404 unless this version belongs to the account (version -> content -> workflow run)."""
    from app.content.models import Content, ContentVersion
    from app.workflows.models import WorkflowRun
    owned = (
        db.query(ContentVersion.id)
        .join(Content, Content.id == ContentVersion.content_id)
        .join(WorkflowRun, WorkflowRun.id == Content.workflow_run_id)
        .filter(ContentVersion.id == version_id, Content.id == content_id, WorkflowRun.owner_id == owner_id)
        .first()
    )
    if owned is None:
        raise HTTPException(status_code=404, detail="Content version not found.")


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
    user: User = Depends(current_user),
):
    """
    Generate an image for a specific ContentVersion through the provider boundary.
    Persists asset safely to storage and records MediaAsset in the database.
    """
    require_owned_version(db, content_id, version_id, user.id)
    from app.accounts.context import set_current_owner
    set_current_owner(user.id)
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
    user: User = Depends(current_user),
):
    """
    List media assets attached to a specific ContentVersion.
    """
    require_owned_version(db, content_id, version_id, user.id)
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
