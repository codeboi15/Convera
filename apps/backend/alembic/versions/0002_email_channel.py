"""email channel: workspace inbound routing + message dedupe

Revision ID: 0002_email
Revises: 0001_initial
Create Date: 2026-08-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_email"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspaces", sa.Column("inbound_key", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "workspaces", sa.Column("support_email", sa.String(length=255), nullable=True)
    )

    # Backfill existing rows from their slug so the column can be NOT NULL.
    op.execute("UPDATE workspaces SET inbound_key = left(slug, 48) WHERE inbound_key IS NULL")
    # Guard against slug collisions after truncation.
    op.execute(
        """
        UPDATE workspaces w SET inbound_key = left(w.slug, 40) || '-' || left(w.id::text, 6)
        WHERE EXISTS (
            SELECT 1 FROM workspaces o
            WHERE o.inbound_key = w.inbound_key AND o.id <> w.id
        )
        """
    )

    op.alter_column("workspaces", "inbound_key", nullable=False)
    op.create_index(
        "ix_workspaces_inbound_key", "workspaces", ["inbound_key"], unique=True
    )

    # Idempotent inbound email: one row per (workspace, Message-ID).
    op.create_index(
        "uq_message_workspace_email_id",
        "messages",
        ["workspace_id", "email_message_id"],
        unique=True,
        postgresql_where=sa.text("email_message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_message_workspace_email_id", table_name="messages")
    op.drop_index("ix_workspaces_inbound_key", table_name="workspaces")
    op.drop_column("workspaces", "support_email")
    op.drop_column("workspaces", "inbound_key")
