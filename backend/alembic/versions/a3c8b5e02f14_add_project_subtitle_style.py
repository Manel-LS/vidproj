"""Add projects.subtitle_style

Which subtitle treatment a video carries, or "none". Kept on the project rather
than only on the plan so it survives a replan: regenerating the script should not
silently switch the subtitles off.

Revision ID: a3c8b5e02f14
Revises: f7a2e4c91d63
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a3c8b5e02f14"
down_revision = "f7a2e4c91d63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing projects were rendered without subtitles; "none" keeps them looking
    # exactly as they did rather than adding a band to work already approved.
    op.add_column(
        "projects",
        sa.Column(
            "subtitle_style",
            sa.String(length=16),
            nullable=False,
            server_default="none",
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "subtitle_style")
