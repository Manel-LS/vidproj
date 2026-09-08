"""Reusable characters, and the description that keeps them consistent.

The point of this service is one rule: **the description is written once and
replayed verbatim**. An image model draws a different person on every call, so
consistency cannot come from re-describing the subject each time — two prompts
built from the same fields by two slightly different code paths already produce
two different children.

`compose_description()` therefore runs only when a character is created or its
fields are edited, and the stored string is what every prompt receives.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.domain.enums import CharacterKind, MediaKind
from app.models import Character, Media, Project, User

MAX_CHARACTERS_PER_USER = 100

#: How each kind opens its description. "A 2-year-old adult" reads wrong, and a
#: model given a contradictory age draws something between the two.
#: No leading article. The description is consumed as "the same {description}",
#: and "the same an adorable toddler" is the kind of malformed phrase that shows
#: up in the generated image.
_KIND_PHRASE = {
    CharacterKind.BABY: "adorable realistic toddler",
    CharacterKind.CHILD: "realistic child",
    CharacterKind.TEEN: "realistic teenager",
    CharacterKind.ADULT: "realistic adult",
    CharacterKind.ELDER: "realistic elderly person",
    CharacterKind.FICTIONAL: "fictional character",
    CharacterKind.ANIMAL: "animal character",
}

#: Articles stripped from the head of a description before it is prefixed.
#: Longest first: with "the " ahead of "the same ", a description already
#: starting "the same ..." came out as "the same same ...".
_ARTICLES = ("the same ", "the ", "an ", "a ")


def compose_description(character: Character) -> str:
    """Build the frozen sentence from the character's fields.

    Empty fields are dropped rather than rendered as blanks: a prompt containing
    "wearing , with hair" degrades the result measurably.
    """
    kind = CharacterKind(character.kind)
    parts: list[str] = []

    opening = _KIND_PHRASE.get(kind, "character")
    if character.age:
        opening += f", {character.age}"
    if character.gender and kind not in (CharacterKind.ANIMAL, CharacterKind.FICTIONAL):
        opening += f", {character.gender}"
    parts.append(opening)

    for label, value in (
        ("", character.skin_tone),
        ("", character.hair),
        ("wearing ", character.clothes),
        ("with ", character.headwear),
        ("", character.expression),
    ):
        if value:
            parts.append(f"{label}{value}")

    sentence = ", ".join(parts)
    if character.environment:
        sentence += f", in {character.environment}"
    return sentence[:1200]


def prompt_prefix(project: Project) -> str:
    """The character clause to put at the head of a scene's image prompt.

    Returns an empty string when the project has no character, so callers can
    concatenate unconditionally.
    """
    character = project.character
    if character is None or not character.description:
        return ""
    # "the same ..." is the instruction that matters: it tells the model this is a
    # returning subject rather than a fresh one. A user-written description may
    # open with an article, so strip it — the phrase has to read as English.
    description = character.description.strip()
    lowered = description.lower()
    for article in _ARTICLES:
        if lowered.startswith(article):
            description = description[len(article):].lstrip()
            break
    return f"the same {description}"


def list_characters(session: Session, user: User) -> list[Character]:
    return list(
        session.scalars(
            select(Character)
            .where(Character.user_id == user.id)
            .order_by(Character.updated_at.desc())
        )
    )


def get_owned_character(session: Session, character_id: str, user: User) -> Character:
    character = session.get(Character, character_id)
    if character is None or character.user_id != user.id:
        raise NotFoundError("That character could not be found.")
    return character


def _apply_fields(character: Character, data: dict) -> None:
    for field in (
        "name", "kind", "age", "gender", "skin_tone", "hair",
        "clothes", "headwear", "expression", "personality", "environment",
    ):
        if field in data and data[field] is not None:
            setattr(character, field, data[field])


def create_character(session: Session, user: User, data: dict) -> Character:
    existing = session.scalar(
        select(Character).where(Character.user_id == user.id).limit(MAX_CHARACTERS_PER_USER)
    )
    if existing is not None and len(user.characters) >= MAX_CHARACTERS_PER_USER:
        raise ValidationError(
            f"You already have the maximum of {MAX_CHARACTERS_PER_USER} saved characters."
        )

    character = Character(user_id=user.id, name=data.get("name") or "Untitled character")
    _apply_fields(character, data)
    # An explicit description wins: a user who wrote their own prompt knows what
    # they want better than a sentence assembled from dropdowns.
    character.description = (data.get("description") or "").strip() or compose_description(character)
    session.add(character)
    session.flush()
    return character


def update_character(session: Session, character: Character, data: dict) -> Character:
    _apply_fields(character, data)
    if data.get("description") is not None:
        supplied = str(data["description"]).strip()
        character.description = supplied or compose_description(character)
    elif any(
        key in data
        for key in ("kind", "age", "gender", "skin_tone", "hair", "clothes", "headwear",
                    "expression", "environment")
    ):
        # Fields changed and no description was supplied: recompose, otherwise the
        # frozen sentence would keep describing the old character.
        character.description = compose_description(character)
    session.flush()
    return character


def set_reference_image(session: Session, character: Character, media: Media | None) -> Character:
    if media is not None:
        if media.user_id != character.user_id:
            raise NotFoundError("That image could not be found.")
        if media.kind != MediaKind.IMAGE.value:
            raise ValidationError("A character reference has to be an image.")
    character.reference_media_id = media.id if media is not None else None
    session.flush()
    return character


def delete_character(session: Session, character: Character) -> None:
    # Projects keep working without their character: the FK is ON DELETE SET NULL,
    # and every scene already holds its own prompt.
    session.delete(character)
    session.flush()


def attach_to_project(session: Session, project: Project, character: Character | None) -> Project:
    project.character_id = character.id if character is not None else None
    session.flush()
    return project
