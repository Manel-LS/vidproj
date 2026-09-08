"""Give voice_overs.word_timings a database-level default

Migration f7a2e4c91d63 added the column as NOT NULL with no server default. That
is fine for code that knows about it — the ORM supplies `[]` — but it breaks any
INSERT that omits the column, and there is always such an INSERT: a server
process started before the deploy is still running the previous mapping, and on
MariaDB the implicit value for an omitted NOT NULL text column is the empty
string, which fails the `json_valid` CHECK that backs a JSON column.

The symptom was a 500 on project creation, because creating a project inserts the
project's voice-over slot.

A NOT NULL column with no server default is a rolling-deploy hazard whatever the
engine, so this is the fix rather than "restart the server".

Revision ID: c1d9f3b7a208
Revises: a3c8b5e02f14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c1d9f3b7a208"
down_revision = "a3c8b5e02f14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "voice_overs",
        "word_timings",
        existing_type=sa.JSON(),
        existing_nullable=False,
        server_default=sa.text("'[]'"),
    )


def downgrade() -> None:
    op.alter_column(
        "voice_overs",
        "word_timings",
        existing_type=sa.JSON(),
        existing_nullable=False,
        server_default=None,
    )
