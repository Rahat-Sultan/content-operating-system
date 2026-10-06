from uuid import UUID
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.content.models import Content, ContentVersion
from app.media.models import MediaAsset, MediaAssetType, MediaAssetStatus
from app.media.factory import get_image_generation_provider, get_media_storage
from app.media.interface import (
    ImageGenerationRequest,
    TransientImageGenerationError,
    PermanentImageGenerationError,
)
from app.media.prompt import construct_image_prompt


def generate_media_for_content_version(
    db: Session,
    content_id: UUID,
    version_id: UUID,
    user_prompt: str | None = None,
    regenerate: bool = False,
) -> MediaAsset:
    """
    Validates content & content_version relationship, handles idempotency,
    generates media via ImageGenerationProvider, persists bytes via MediaStorage,
    and records MediaAsset in PostgreSQL.
    """
    # 1. Validate Content exists
    content = db.query(Content).filter(Content.id == content_id).first()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Content {content_id} not found."
        )

    # 2. Validate ContentVersion exists and belongs to this Content
    version = (
        db.query(ContentVersion)
        .filter(ContentVersion.id == version_id, ContentVersion.content_id == content_id)
        .first()
    )
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ContentVersion {version_id} does not belong to Content {content_id}."
        )

    # 3. Check for existing media asset (Idempotency)
    existing_asset = (
        db.query(MediaAsset)
        .filter(MediaAsset.content_version_id == version_id, MediaAsset.status == MediaAssetStatus.READY)
        .order_by(MediaAsset.created_at.desc())
        .first()
    )
    if existing_asset and not regenerate:
        # Idempotent return of already generated ready asset for this version
        return existing_asset

    # 4. Construct prompt from Strategy + Brief + Version context
    final_prompt = construct_image_prompt(
        db=db,
        content=content,
        version=version,
        user_override_prompt=user_prompt,
    )

    # 5. Invoke Provider
    provider = get_image_generation_provider()
    req = ImageGenerationRequest(
        content_version_id=version.id,
        prompt=final_prompt,
        title=version.title,
    )

    try:
        gen_result = provider.generate_image(req)
    except TransientImageGenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Transient failure generating image: {str(e)}"
        )
    except PermanentImageGenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Image generation failed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during image generation: {str(e)}"
        )

    # 6. Store the image. Supabase when configured (public, unguessable path, per-account folder);
    #    otherwise the local media folder. The per-account limit applies to both.
    from app.media import supabase_storage
    from app.workflows.models import WorkflowRun
    from app.content.models import Content
    owner_id = (db.query(WorkflowRun.owner_id).join(Content, Content.workflow_run_id == WorkflowRun.id)
                .filter(Content.id == content.id).scalar())
    supabase_storage.check_quota(db, owner_id, len(gen_result.data))
    if supabase_storage.configured():
        public_url, size_bytes = supabase_storage.upload(owner_id, gen_result.data, gen_result.mime_type)
        class _Stored:
            storage_url = public_url
        stored = _Stored()
        stored.size_bytes = size_bytes
    else:
        storage = get_media_storage()
        try:
            stored = storage.save(
                filename=f"{version.id}.png",
                data=gen_result.data,
                mime_type=gen_result.mime_type,
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Storage boundary failure: {str(e)}"
            )

    # 7. Persist MediaAsset row
    media_asset = MediaAsset(
        content_version_id=version.id,
        type=MediaAssetType.IMAGE,
        status=MediaAssetStatus.READY,
        storage_url=stored.storage_url,
        mime_type=gen_result.mime_type,
        width=gen_result.width,
        height=gen_result.height,
        alt_text=gen_result.alt_text,
        prompt=final_prompt,
        provider=gen_result.provider,
        provider_asset_id=gen_result.provider_asset_id,
        asset_metadata={
            **gen_result.metadata,
            "is_stub": gen_result.is_stub,
            "size_bytes": stored.size_bytes,
        },
    )

    db.add(media_asset)
    db.commit()
    db.refresh(media_asset)
    return media_asset


def get_media_assets_for_content_version(
    db: Session,
    content_id: UUID,
    version_id: UUID,
) -> list[MediaAsset]:
    """Retrieves all media assets attached to a content version."""
    version = (
        db.query(ContentVersion)
        .filter(ContentVersion.id == version_id, ContentVersion.content_id == content_id)
        .first()
    )
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ContentVersion {version_id} not found for Content {content_id}."
        )

    return (
        db.query(MediaAsset)
        .filter(MediaAsset.content_version_id == version_id)
        .order_by(MediaAsset.created_at.desc())
        .all()
    )
