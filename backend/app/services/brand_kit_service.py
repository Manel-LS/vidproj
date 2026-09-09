"""Brand kits: a brand's constants, and where they get applied.

The rule this service holds is that a brand kit is **applied, never merged**. When
a project uses a kit, the kit's colours and typography win over the style preset's
— that is the whole point of having one. What it does not touch is anything the
user wrote: a hook, a CTA or a caption they typed stays theirs, whatever brand it
is filed under.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.domain.enums import MediaKind
from app.models import BrandKit, Media, Project, User

MAX_KITS_PER_USER = 50

LOGO_POSITIONS = ("top_left", "top_right", "bottom_left", "bottom_right")

_FIELDS = (
    "name", "brand_name", "slogan", "primary_color", "accent_color",
    "background_color", "font_family", "logo_position", "logo_scale", "logo_opacity",
)


def list_kits(session: Session, user: User) -> list[BrandKit]:
    return list(
        session.scalars(
            select(BrandKit).where(BrandKit.user_id == user.id).order_by(BrandKit.updated_at.desc())
        )
    )


def get_owned_kit(session: Session, kit_id: str, user: User) -> BrandKit:
    kit = session.get(BrandKit, kit_id)
    if kit is None or kit.user_id != user.id:
        # Indistinguishable from one that does not exist, so ownership cannot be probed.
        raise NotFoundError("That brand kit could not be found.")
    return kit


def _apply_fields(kit: BrandKit, data: dict) -> None:
    for field in _FIELDS:
        if field in data and data[field] is not None:
            setattr(kit, field, data[field])
    if kit.logo_position not in LOGO_POSITIONS:
        kit.logo_position = "top_right"


def create_kit(session: Session, user: User, data: dict) -> BrandKit:
    if len(user.brand_kits) >= MAX_KITS_PER_USER:
        raise ValidationError(f"You already have the maximum of {MAX_KITS_PER_USER} brand kits.")

    kit = BrandKit(user_id=user.id, name=(data.get("name") or "Untitled brand").strip())
    _apply_fields(kit, data)
    session.add(kit)
    session.flush()
    return kit


def update_kit(session: Session, kit: BrandKit, data: dict) -> BrandKit:
    _apply_fields(kit, data)
    session.flush()
    return kit


def set_logo(session: Session, kit: BrandKit, media: Media | None) -> BrandKit:
    if media is not None:
        if media.user_id != kit.user_id:
            raise NotFoundError("That image could not be found.")
        if media.kind != MediaKind.IMAGE.value:
            raise ValidationError("A logo has to be an image.")
    kit.logo_media_id = media.id if media is not None else None
    session.flush()
    return kit


def delete_kit(session: Session, kit: BrandKit) -> None:
    # Projects keep working: the foreign key is ON DELETE SET NULL, and a plan
    # already holds the colours it was built with.
    session.delete(kit)
    session.flush()


def kit_of(project: Project) -> BrandKit | None:
    return project.brand_kit
