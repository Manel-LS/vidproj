"""Add voice_overs.word_timings

Word-level subtitles need to know when each word is spoken. Edge reports that
during synthesis and nowhere else, so the timings have to be captured as the
audio is produced — recovering them later would mean synthesising the whole
narration again.

Existing rows get an empty list, which is the honest value: those narrations
were produced before the timings were asked for, and the renderer degrades to
sentence-level subtitles rather than guessing where the words fell.

Revision ID: f7a2e4c91d63
Revises: e5b7c9d34f82
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f7a2e4c91d63"
down_revision = "e5b7c9d34f82"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Three steps rather than one NOT NULL add: the table already has rows, and
    # MySQL/MariaDB will not take a literal DEFAULT on a JSON column, so a direct
    # NOT NULL add either fails or silently fills the rows with an empty string
    # that is not valid JSON.
    op.add_column("voice_overs", sa.Column("word_timings", sa.JSON(), nullable=True))
    op.execute("UPDATE voice_overs SET word_timings = '[]' WHERE word_timings IS NULL")
    op.alter_column(
        "voice_overs", "word_timings", existing_type=sa.JSON(), nullable=False
    )


def downgrade() -> None:
    op.drop_column("voice_overs", "word_timings")
