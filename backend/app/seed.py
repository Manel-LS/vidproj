"""Seed data: a demo account with a ready-to-render project.

Run with `python -m app.seed`. Idempotent — running it twice will not duplicate the
demo user or its project.

The sample images and the audio bed are generated procedurally (see
`infrastructure.imaging.samples`), so nothing copyrighted is bundled with the product.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.base import Base, engine, session_scope
from app.domain.enums import Platform, VideoStyle
from app.domain.templates import BUILTIN_TEMPLATES
from app.infrastructure.imaging.samples import generate_sample_image, generate_silent_wav
from app.models import Project, Template, User
from app.services import auth_service, media_service, plan_service, project_service

logger = get_logger("seed")

DEMO_PROJECT_NAME = "New school supplies collection"

SAMPLE_LABELS = (
    "NOTEBOOKS",
    "PENS & PENCILS",
    "BACKPACKS",
    "DESK SET",
)


def sync_templates(session) -> int:
    """Mirror the built-in template catalogue into the database.

    The renderer reads templates from the domain, not from these rows; the table
    exists so user-saved templates have somewhere to live alongside the built-ins,
    and so an admin can see the catalogue.
    """
    created = 0
    for template in BUILTIN_TEMPLATES:
        existing = session.scalar(
            select(Template).where(Template.key == template.key, Template.user_id.is_(None))
        )
        definition = {
            "slots": [
                {
                    "kind": slot.kind,
                    "duration": slot.duration,
                    "animation": slot.animation.value if slot.animation else None,
                    "transition": slot.transition.value if slot.transition else None,
                    "text_role": slot.text_role.value if slot.text_role else None,
                    "text_template": slot.text_template,
                    "text_position": slot.text_position.value if slot.text_position else None,
                    "text_animation": slot.text_animation.value if slot.text_animation else None,
                    "repeat": slot.repeat,
                    "needs_image": slot.needs_image,
                }
                for slot in template.slots
            ]
        }
        if existing is None:
            session.add(
                Template(
                    key=template.key,
                    name=template.name,
                    description=template.description,
                    category=template.category,
                    style=template.style.value,
                    format=template.format.value,
                    recommended_duration=template.recommended_duration,
                    min_images=template.min_images,
                    max_images=template.max_images,
                    is_builtin=True,
                    definition=definition,
                )
            )
            created += 1
        else:
            existing.name = template.name
            existing.description = template.description
            existing.category = template.category
            existing.definition = definition
    session.flush()
    return created


def seed_demo_user(session) -> User:
    user = auth_service.get_by_email(session, settings.seed_demo_user_email)
    if user is not None:
        logger.info("Demo user already exists: %s", user.email)
        return user

    user = auth_service.register(
        session,
        email=settings.seed_demo_user_email,
        password=settings.seed_demo_user_password,
        full_name="Demo Creator",
    )
    logger.info("Created demo user %s", user.email)
    return user


def seed_demo_project(session, user: User) -> Project:
    existing = session.scalar(
        select(Project).where(Project.user_id == user.id, Project.name == DEMO_PROJECT_NAME)
    )
    if existing is not None:
        logger.info("Demo project already exists (%s)", existing.id)
        return existing

    project = project_service.create_project(
        session,
        user,
        name=DEMO_PROJECT_NAME,
        description=(
            "Back-to-school launch for our new stationery range. Energetic, colourful, "
            "aimed at parents shopping in the last week of August."
        ),
        topic="school supplies",
        platform=Platform.TIKTOK,
        style=VideoStyle.TIKTOK_TREND,
        template_key="product_tiktok",
        target_duration=12.0,
    )

    for index, label in enumerate(SAMPLE_LABELS):
        media_service.add_image(
            session,
            project,
            media_service.UploadPayload(
                filename=f"sample-{index + 1}.jpg",
                content_type="image/jpeg",
                data=generate_sample_image(index, label=label),
            ),
        )

    media_service.add_audio(
        session,
        project,
        media_service.UploadPayload(
            filename="demo-bed.wav",
            content_type="audio/wav",
            data=generate_silent_wav(14.0),
        ),
        source="sample",
    )
    session.flush()

    audio = [m for m in project.media if m.kind == "audio"]
    if audio and project.audio_track is not None:
        project.audio_track.media_id = audio[0].id

    outcome = plan_service.generate_plan(
        project,
        instruction="Energetic back-to-school promo for parents.",
        target_duration=12.0,
        use_ai=False,
    )
    plan_service.apply_plan(session, project, outcome.plan)
    session.flush()

    logger.info(
        "Created demo project %s with %s images and %s scenes",
        project.id,
        len(SAMPLE_LABELS),
        len(project.scenes),
    )
    return project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the Reelcraft database.")
    parser.add_argument(
        "--create-tables",
        action="store_true",
        help="Create tables directly instead of relying on Alembic (development only).",
    )
    parser.add_argument("--templates-only", action="store_true", help="Only sync templates.")
    args = parser.parse_args(argv)

    configure_logging()

    import app.models  # noqa: F401

    if args.create_tables or settings.is_sqlite:
        # SQLite has no migration story worth the ceremony in development; a real
        # database server is migrated with Alembic instead.
        Base.metadata.create_all(engine)
    else:
        from sqlalchemy import inspect

        if not inspect(engine).has_table("users"):
            logger.error(
                "The %s schema has not been created yet. Run `alembic upgrade head` "
                "first (or pass --create-tables to build it directly).",
                settings.database_backend,
            )
            return 1

    session = session_scope()
    try:
        created = sync_templates(session)
        logger.info("Templates synced (%s new).", created)

        if not args.templates_only:
            user = seed_demo_user(session)
            seed_demo_project(session, user)

        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Seeding failed")
        return 1
    finally:
        session.close()

    if not args.templates_only:
        print()
        print("  Demo account ready")
        print(f"    email:    {settings.seed_demo_user_email}")
        print(f"    password: {settings.seed_demo_user_password}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
