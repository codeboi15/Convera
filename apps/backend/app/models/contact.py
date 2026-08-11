from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin


class Contact(UUIDMixin, TimestampMixin, Base):
    """An end-user (website visitor / email sender) within a workspace."""

    __tablename__ = "contacts"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    email: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    # Anonymous widget visitor id (stored client-side in localStorage).
    external_id: Mapped[Optional[str]] = mapped_column(String(128))
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    attributes: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "external_id", name="uq_contact_workspace_external"
        ),
        # One contact per email per workspace (only when email is present).
        Index(
            "uq_contact_workspace_email",
            "workspace_id",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
    )
