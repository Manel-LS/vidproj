"""Add characters, and projects.character_id

A reusable subject that stays visually consistent between videos: a frozen
description replayed verbatim into every prompt, plus a reference image for the
providers that accept one.

Revision ID: c8d2f5a71b30
Revises: b1c4e7f20a91
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c8d2f5a71b30"
down_revision = "b1c4e7f20a91"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "characters",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="adult"),
        sa.Column("age", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("gender", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("skin_tone", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("hair", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("clothes", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("headwear", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("expression", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("personality", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("environment", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("description", sa.String(length=1200), nullable=False, server_default=""),
        sa.Column("reference_media_id", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reference_media_id"], ["media.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_characters_user_id", "characters", ["user_id"])
    op.create_index("ix_characters_user_updated", "characters", ["user_id", "updated_at"])

    op.add_column("projects", sa.Column("character_id", sa.String(length=32), nullable=True))
    op.create_foreign_key(
        "fk_projects_character_id", "projects", "characters", ["character_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_projects_character_id", "projects", type_="foreignkey")
    op.drop_column("projects", "character_id")
    op.drop_index("ix_characters_user_updated", table_name="characters")
    op.drop_index("ix_characters_user_id", table_name="characters")
    op.drop_table("characters")
