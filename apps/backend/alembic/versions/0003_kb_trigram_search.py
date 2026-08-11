"""enable pg_trgm for fuzzy knowledge-base search

Revision ID: 0003_trgm
Revises: 0002_email
Create Date: 2026-08-11

Full-text search alone misses typos and partial words ("refnd", "cant login"),
which matters most in the chat widget where suggestions are produced while the
visitor is still typing. Trigram similarity covers that gap.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0003_trgm"
down_revision: Union[str, None] = "0002_email"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # GIN trigram index on titles — the field users actually search by.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_kb_articles_title_trgm "
        "ON kb_articles USING gin (lower(title) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kb_articles_title_trgm")
    # The extension is left installed; other features may rely on it.
