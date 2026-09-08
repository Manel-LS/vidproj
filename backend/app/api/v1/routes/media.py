from __future__ import annotations

from fastapi import APIRouter, Depends, File, Path, UploadFile, status

from app.api.deps import CurrentUser, SessionDep, rate_limit, upload_rate_limit
from app.api.serializers import serialize_audio, serialize_media
from app.core.config import settings
from app.core.errors import ValidationError
from app.domain.enums import MediaKind
from app.schemas.media import (
    AudioTrackResponse,
    AudioTrackUpdate,
    CropRequest,
    LibraryTrack,
    MediaResponse,
    ReorderMediaRequest,
)
from app.services import media_service, project_service, scene_service

router = APIRouter(prefix="/projects/{project_id}", tags=["media"])

MAX_FILES_PER_REQUEST = 20


@router.post(
    "/media",
    response_model=list[MediaResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload images",
    dependencies=[Depends(upload_rate_limit)],
)
def upload_images(
    session: SessionDep,
    user: CurrentUser,
    project_id: str = Path(...),
    files: list[UploadFile] = File(..., description="JPG, PNG or WEBP images"),
) -> list[MediaResponse]:
    """Upload one or more images. Each file is validated, optimised and analysed."""
    project = project_service.get_owned_project(session, project_id, user)
    if not files:
        raise ValidationError("Please choose at least one image to upload.")
    if len(files) > MAX_FILES_PER_REQUEST:
        raise ValidationError(
            f"Please upload at most {MAX_FILES_PER_REQUEST} images at a time."
        )

    created = []
    for upload in files:
        data = media_service.read_upload(
            upload,
            max_bytes=settings.max_image_bytes,
            label=f"'{upload.filename or 'image'}'",
        )
        media = media_service.add_image(
            session,
            project,
            media_service.UploadPayload(
                filename=upload.filename or "image.jpg",
                content_type=upload.content_type or "",
                data=data,
            ),
        )
        created.append(media)

        # A newly uploaded image gets a scene, so the timeline is never empty after
        # an upload — the single most common source of "nothing happened" confusion.
        scene_service.create_scene(session, project, media_id=media.id)

    session.commit()
    return [serialize_media(media) for media in created]


@router.get("/media", response_model=list[MediaResponse], summary="List project media",
            dependencies=[Depends(rate_limit)])
def list_media(project_id: str, session: SessionDep, user: CurrentUser) -> list[MediaResponse]:
    project = project_service.get_owned_project(session, project_id, user)
    return [
        serialize_media(media)
        for media in sorted(project.media, key=lambda m: (m.kind, m.position, m.created_at))
    ]


@router.post("/media/reorder", response_model=list[MediaResponse], summary="Reorder images",
             dependencies=[Depends(rate_limit)])
def reorder_media(
    project_id: str, payload: ReorderMediaRequest, session: SessionDep, user: CurrentUser
) -> list[MediaResponse]:
    project = project_service.get_owned_project(session, project_id, user)
    ordered = media_service.reorder_images(session, project, payload.media_ids)
    session.commit()
    return [serialize_media(media) for media in ordered]


@router.put(
    "/media/{media_id}",
    response_model=MediaResponse,
    summary="Replace an image, keeping its id",
    dependencies=[Depends(upload_rate_limit)],
)
def replace_image(
    project_id: str,
    media_id: str,
    session: SessionDep,
    user: CurrentUser,
    file: UploadFile = File(...),
) -> MediaResponse:
    project = project_service.get_owned_project(session, project_id, user)
    media = media_service.get_media(session, media_id, user_id=user.id)
    if media.project_id != project.id or media.kind != MediaKind.IMAGE.value:
        raise ValidationError("That image is not part of this project.")

    data = media_service.read_upload(
        file, max_bytes=settings.max_image_bytes, label=f"'{file.filename or 'image'}'"
    )
    updated = media_service.replace_image(
        session,
        project,
        media,
        media_service.UploadPayload(
            filename=file.filename or "image.jpg",
            content_type=file.content_type or "",
            data=data,
        ),
    )
    session.commit()
    return serialize_media(updated)


@router.post("/media/{media_id}/crop", response_model=MediaResponse, summary="Crop an image",
             dependencies=[Depends(rate_limit)])
def crop_media(
    project_id: str,
    media_id: str,
    payload: CropRequest,
    session: SessionDep,
    user: CurrentUser,
) -> MediaResponse:
    project = project_service.get_owned_project(session, project_id, user)
    media = media_service.get_media(session, media_id, user_id=user.id)
    if media.project_id != project.id:
        raise ValidationError("That image is not part of this project.")
    updated = media_service.crop_media(
        session, media, x=payload.x, y=payload.y, width=payload.width, height=payload.height
    )
    session.commit()
    return serialize_media(updated)


@router.delete(
    "/media/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a media file",
    dependencies=[Depends(rate_limit)],
)
def delete_media(project_id: str, media_id: str, session: SessionDep, user: CurrentUser) -> None:
    project = project_service.get_owned_project(session, project_id, user)
    media = media_service.get_media(session, media_id, user_id=user.id)
    if media.project_id != project.id:
        raise ValidationError("That file is not part of this project.")

    # Scenes pointing at this image lose their media rather than being deleted, so the
    # user's timing and copy survive; the editor shows them as needing an image.
    for scene in project.scenes:
        if scene.media_id == media.id:
            scene.media_id = None
    if project.audio_track and project.audio_track.media_id == media.id:
        project.audio_track.media_id = None
    if project.voice_over and project.voice_over.media_id == media.id:
        project.voice_over.media_id = None

    media_service.delete_media(session, media)
    session.commit()


# ---------------------------------------------------------------- audio ------


@router.post(
    "/audio",
    response_model=AudioTrackResponse,
    summary="Upload background music",
    dependencies=[Depends(upload_rate_limit)],
)
def upload_audio(
    project_id: str,
    session: SessionDep,
    user: CurrentUser,
    file: UploadFile = File(..., description="MP3 or WAV"),
) -> AudioTrackResponse:
    project = project_service.get_owned_project(session, project_id, user)
    data = media_service.read_upload(
        file, max_bytes=settings.max_audio_bytes, label=f"'{file.filename or 'audio'}'"
    )
    media = media_service.add_audio(
        session,
        project,
        media_service.UploadPayload(
            filename=file.filename or "track.mp3",
            content_type=file.content_type or "",
            data=data,
        ),
    )
    track = project.audio_track
    old_media_id = track.media_id if track else None
    if track is not None:
        track.media_id = media.id
        track.library_track_key = None
    session.commit()

    if old_media_id and old_media_id != media.id:
        old = session.get(type(media), old_media_id)
        if old is not None:
            media_service.delete_media(session, old)
            session.commit()

    session.refresh(project)
    return serialize_audio(project.audio_track)


@router.patch("/audio", response_model=AudioTrackResponse, summary="Update audio settings",
              dependencies=[Depends(rate_limit)])
def update_audio(
    project_id: str, payload: AudioTrackUpdate, session: SessionDep, user: CurrentUser
) -> AudioTrackResponse:
    project = project_service.get_owned_project(session, project_id, user)
    track = project.audio_track
    if track is None:
        raise ValidationError("This project has no audio slot.")

    changes = payload.model_dump(exclude_unset=True)
    if changes.pop("clear", False):
        track.media_id = None
        track.library_track_key = None
    if "media_id" in changes and changes["media_id"] is not None:
        media = media_service.get_media(session, changes["media_id"], user_id=user.id)
        if media.project_id != project.id or media.kind != MediaKind.AUDIO.value:
            raise ValidationError("That audio track is not part of this project.")
        track.media_id = media.id
    changes.pop("media_id", None)
    for field, value in changes.items():
        if value is not None:
            setattr(track, field, value)

    session.commit()
    session.refresh(project)
    return serialize_audio(project.audio_track)


@router.get(
    "/audio/library",
    response_model=list[LibraryTrack],
    summary="Royalty-free music library",
    dependencies=[Depends(rate_limit)],
)
def music_library(project_id: str, session: SessionDep, user: CurrentUser) -> list[LibraryTrack]:
    """The catalogue slot for licensed music.

    Reelcraft ships no bundled music: distributing tracks without a licence is not
    something this product will do. The endpoint exists so the UI has a stable shape to
    render once a licensed catalogue is connected.
    """
    project_service.get_owned_project(session, project_id, user)
    return []
