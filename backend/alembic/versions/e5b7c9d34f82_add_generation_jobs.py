"""Add generation_jobs

Progress used to live in three shapes: render_jobs for renders, a JSON blob on
the scene for AI Motion and lip sync, a column on voice_overs for narration.
Nothing could answer "what is this project doing right now".

Revision ID: e5b7c9d34f82
Revises: d3f9a1c60e57
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e5b7c9d34f82"
down_revision = "d3f9a1c60e57"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("scene_id", sa.String(length=32), nullable=True),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage", sa.String(length=80), nullable=False, server_default="Queued"),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("external_job_id", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("result_media_id", sa.String(length=32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_generation_jobs_project_id", "generation_jobs", ["project_id"])
    op.create_index("ix_generation_jobs_user_id", "generation_jobs", ["user_id"])
    op.create_index("ix_generation_jobs_status", "generation_jobs", ["status"])
    op.create_index(
        "ix_generation_jobs_project_created", "generation_jobs", ["project_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("generation_jobs")
