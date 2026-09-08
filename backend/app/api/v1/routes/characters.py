"""Reusable characters: CRUD, reference image, and attaching one to a project."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.deps import CurrentUser, SessionDep, rate_limit
from app.core.config import settings
from app.core.errors import NotFoundError
from app.infrastructure.storage.factory import get_storage
from app.models import Character
from app.schemas.character import CharacterCreate, CharacterResponse, CharacterUpdate
from app.services import character_service, media_service, project_service

router = APIRouter(prefix="/characters", tags=["characters"], dependencies=[Depends(rate_limit)])


def serialize_character(character: Character) -> CharacterResponse:
    url = None
    if character.reference_media is not None:
        media = character.reference_media
        url = get_storage().get_url(media.thumbnail_key or media.storage_key)
    return CharacterResponse.model_validate(
        {
            "id": character.id,
            "name": character.name,
            "kind": character.kind,
            "age": character.age,
            "gender": character.gender,
            "skin_tone": character.skin_tone,
            "hair": character.hair,
            "clothes": character.clothes,
            "headwear": character.headwear,
            "expression": character.expression,
            "personality": character.personality,
            "environment": character.environment,
            "description": character.description,
            "reference_media_id": character.reference_media_id,
            "reference_image_url": url,
            "created_at": character.created_at,
            "updated_at": character.updated_at,
        }
    )


@router.get("", response_model=list[CharacterResponse], summary="List your saved characters")
def list_characters(session: SessionDep, user: CurrentUser) -> list[CharacterResponse]:
    return [serialize_character(c) for c in character_service.list_characters(session, user)]


@router.post(
    "",
    response_model=CharacterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a reusable character",
)
def create_character(
    payload: CharacterCreate, session: SessionDep, user: CurrentUser
) -> CharacterResponse:
    character = character_service.create_character(session, user, payload.model_dump())
    session.commit()
    session.refresh(character)
    return serialize_character(character)


@router.get("/{character_id}", response_model=CharacterResponse, summary="Read one character")
def get_character(character_id: str, session: SessionDep, user: CurrentUser) -> CharacterResponse:
    return serialize_character(character_service.get_owned_character(session, character_id, user))


@router.patch("/{character_id}", response_model=CharacterResponse, summary="Update a character")
def update_character(
    character_id: str, payload: CharacterUpdate, session: SessionDep, user: CurrentUser
) -> CharacterResponse:
    character = character_service.get_owned_character(session, character_id, user)
    character_service.update_character(
        session, character, payload.model_dump(exclude_unset=True)
    )
    session.commit()
    session.refresh(character)
    return serialize_character(character)


@router.delete(
    "/{character_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a character",
)
def delete_character(character_id: str, session: SessionDep, user: CurrentUser) -> None:
    character = character_service.get_owned_character(session, character_id, user)
    character_service.delete_character(session, character)
    session.commit()


@router.post(
    "/{character_id}/reference",
    response_model=CharacterResponse,
    summary="Upload the character's reference image",
)
def upload_reference(
    character_id: str,
    session: SessionDep,
    user: CurrentUser,
    file: UploadFile = File(...),
) -> CharacterResponse:
    """Store the picture that providers use to keep the subject recognisable.

    The image is attached to the user rather than to a project: a character is
    reused across videos, so its reference cannot live inside one of them.
    """
    character = character_service.get_owned_character(session, character_id, user)
    data = media_service.read_upload(
        file, max_bytes=settings.max_image_bytes, label=f"'{file.filename or 'image'}'"
    )
    # `add_image` needs a project to file the media under; a character reference
    # belongs to whichever project the user is working in, so we take the most
    # recent one. Without any project there is nowhere to put it yet.
    project = project_service.most_recent_project(session, user)
    if project is None:
        raise NotFoundError("Create a project before uploading a character reference.")

    media = media_service.add_image(
        session,
        project,
        media_service.UploadPayload(
            filename=file.filename or "reference.jpg",
            content_type=file.content_type or "",
            data=data,
        ),
        source="character_reference",
    )
    character_service.set_reference_image(session, character, media)
    session.commit()
    session.refresh(character)
    return serialize_character(character)
