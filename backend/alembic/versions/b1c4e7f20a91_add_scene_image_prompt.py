"""Add scenes.image_prompt

The prompt handed to the image provider lives on the scene so that regenerating
an image reproduces the same shot. It was briefly squatting in `note`, capped at
400 characters, where a realistic prompt was truncated mid-sentence.

Revision ID: b1c4e7f20a91
Revises: 0509ad8014d0
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b1c4e7f20a91"
down_revision = "0509ad8014d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scenes",
        sa.Column("image_prompt", sa.String(length=1200), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("scenes", "image_prompt")
