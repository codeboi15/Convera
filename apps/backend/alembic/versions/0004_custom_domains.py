"""custom domain verification and certificate state

Revision ID: 0004_domains
Revises: 0003_trgm
Create Date: 2026-08-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_domains"
down_revision: Union[str, None] = "0003_trgm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("custom_domain_token", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "workspaces",
        sa.Column(
            "custom_domain_verified_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "workspaces",
        sa.Column(
            "custom_domain_ssl_status",
            sa.String(length=20),
            nullable=False,
            server_default="none",
        ),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "custom_domain_ssl_status")
    op.drop_column("workspaces", "custom_domain_verified_at")
    op.drop_column("workspaces", "custom_domain_token")
