"""Add projects.language

The planner is told which language to write in, the voice-over picks a matching
voice, and the subtitle renderer needs to know the script runs right to left.
Nothing carried that before; every project was implicitly English.

Revision ID: d3f9a1c60e57
Revises: c8d2f5a71b30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d3f9a1c60e57"
down_revision = "c8d2f5a71b30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("language", sa.String(length=8), nullable=False, server_default="en"),
    )


def downgrade() -> None:
    op.drop_column("projects", "language")
