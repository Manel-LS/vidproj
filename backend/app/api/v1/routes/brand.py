"""Brand kits: CRUD and the logo upload."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.deps import CurrentUser, SessionDep, rate_limit
from app.core.config import settings
from app.core.errors import NotFoundError
from app.infrastructure.storage.factory import get_storage
from app.models import BrandKit
from app.schemas.brand import BrandKitCreate, BrandKitResponse, BrandKitUpdate
from app.services import brand_kit_service, media_service, project_service

router = APIRouter(prefix="/brand-kits", tags=["brand"], dependencies=[Depends(rate_limit)])


def serialize_kit(kit: BrandKit) -> BrandKitResponse:
    url = None
    if kit.logo_media is not None:
        url = get_storage().get_url(kit.logo_media.storage_key)
    return BrandKitResponse.model_validate(
        {
            "id": kit.id,
            "name": kit.name,
            "brand_name": kit.brand_name,
            "slogan": kit.slogan,
            "primary_color": kit.primary_color,
            "accent_color": kit.accent_color,
            "background_color": kit.background_color,
            "font_family": kit.font_family,
            "logo_media_id": kit.logo_media_id,
            "logo_url": url,
            "logo_position": kit.logo_position,
            "logo_scale": kit.logo_scale,
            "logo_opacity": kit.logo_opacity,
            "created_at": kit.created_at,
            "updated_at": kit.updated_at,
        }
    )


@router.get("", response_model=list[BrandKitResponse], summary="List your brand kits")
def list_kits(session: SessionDep, user: CurrentUser) -> list[BrandKitResponse]:
    return [serialize_kit(kit) for kit in brand_kit_service.list_kits(session, user)]


@router.post(
    "",
    response_model=BrandKitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a brand kit",
)
def create_kit(payload: BrandKitCreate, session: SessionDep, user: CurrentUser) -> BrandKitResponse:
    kit = brand_kit_service.create_kit(session, user, payload.model_dump())
    session.commit()
    session.refresh(kit)
    return serialize_kit(kit)


@router.get("/{kit_id}", response_model=BrandKitResponse, summary="Read one brand kit")
def get_kit(kit_id: str, session: SessionDep, user: CurrentUser) -> BrandKitResponse:
    return serialize_kit(brand_kit_service.get_owned_kit(session, kit_id, user))


@router.patch("/{kit_id}", response_model=BrandKitResponse, summary="Update a brand kit")
def update_kit(
    kit_id: str, payload: BrandKitUpdate, session: SessionDep, user: CurrentUser
) -> BrandKitResponse:
    kit = brand_kit_service.get_owned_kit(session, kit_id, user)
    brand_kit_service.update_kit(session, kit, payload.model_dump(exclude_unset=True))
    session.commit()
    session.refresh(kit)
    return serialize_kit(kit)


@router.delete(
    "/{kit_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a brand kit",
)
def delete_kit(kit_id: str, session: SessionDep, user: CurrentUser) -> None:
    kit = brand_kit_service.get_owned_kit(session, kit_id, user)
    brand_kit_service.delete_kit(session, kit)
    session.commit()


@router.post("/{kit_id}/logo", response_model=BrandKitResponse, summary="Upload the logo")
def upload_logo(
    kit_id: str, session: SessionDep, user: CurrentUser, file: UploadFile = File(...)
) -> BrandKitResponse:
    """Store the mark overlaid on every video made with this kit.

    A logo belongs to the brand, not to a project, but `add_image` files media
    under a project — so it goes to the most recent one, exactly as a character
    reference does.
    """
    kit = brand_kit_service.get_owned_kit(session, kit_id, user)
    data = media_service.read_upload(
        file, max_bytes=settings.max_image_bytes, label=f"'{file.filename or 'logo'}'"
    )
    project = project_service.most_recent_project(session, user)
    if project is None:
        raise NotFoundError("Create a project before uploading a logo.")

    media = media_service.add_image(
        session,
        project,
        media_service.UploadPayload(
            filename=file.filename or "logo.png",
            content_type=file.content_type or "",
            data=data,
        ),
        source="brand_logo",
    )
    brand_kit_service.set_logo(session, kit, media)
    session.commit()
    session.refresh(kit)
    return serialize_kit(kit)
