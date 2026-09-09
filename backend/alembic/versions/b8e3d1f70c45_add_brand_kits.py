"""Add brand_kits and projects.brand_kit_id

A brand's constants — name, slogan, colours, logo — kept once and reused, so
every video made for that brand looks like the same brand. Reused across
projects like a character is, and for the same reason: the value is that it does
not change between videos.

Revision ID: b8e3d1f70c45
Revises: c1d9f3b7a208
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b8e3d1f70c45"
down_revision = "c1d9f3b7a208"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brand_kits",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("brand_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("slogan", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("primary_color", sa.String(length=9), nullable=False, server_default="#FFFFFF"),
        sa.Column("accent_color", sa.String(length=9), nullable=False, server_default="#FFD166"),
        sa.Column("background_color", sa.String(length=9), nullable=False, server_default="#101014"),
        sa.Column("font_family", sa.String(length=16), nullable=False, server_default="sans_bold"),
        sa.Column("logo_media_id", sa.String(length=32), nullable=True),
        sa.Column("logo_position", sa.String(length=16), nullable=False, server_default="top_right"),
        sa.Column("logo_scale", sa.Float(), nullable=False, server_default="0.16"),
        sa.Column("logo_opacity", sa.Float(), nullable=False, server_default="0.9"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["logo_media_id"], ["media.id"],
            name="fk_brand_kits_logo_media", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_brand_kits_user_id", "brand_kits", ["user_id"])
    op.create_index("ix_brand_kits_user_updated", "brand_kits", ["user_id", "updated_at"])

    # Nullable, so every existing project keeps rendering exactly as it does now.
    op.add_column("projects", sa.Column("brand_kit_id", sa.String(length=32), nullable=True))
    op.create_foreign_key(
        "fk_projects_brand_kit", "projects", "brand_kits", ["brand_kit_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_projects_brand_kit", "projects", type_="foreignkey")
    op.drop_column("projects", "brand_kit_id")
    op.drop_index("ix_brand_kits_user_updated", table_name="brand_kits")
    op.drop_index("ix_brand_kits_user_id", table_name="brand_kits")
    op.drop_table("brand_kits")
