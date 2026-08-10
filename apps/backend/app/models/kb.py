from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Computed,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.models.enums import ArticleStatus


class KBCategory(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "kb_categories"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    position: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_kbcat_workspace_slug"),
    )


class KBArticle(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "kb_articles"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("kb_categories.id", ondelete="SET NULL"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Plain-text projection of the article, used for search + AI context.
    body_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[ArticleStatus] = mapped_column(
        SAEnum(ArticleStatus, name="article_status"),
        default=ArticleStatus.draft,
        server_default=ArticleStatus.draft.value,
        index=True,
        nullable=False,
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Postgres-maintained full-text index (STORED generated column).
    search_vector: Mapped[Optional[str]] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(body_text, ''))",
            persisted=True,
        ),
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_kbarticle_workspace_slug"),
        Index(
            "ix_kb_articles_search_vector",
            "search_vector",
            postgresql_using="gin",
        ),
    )
