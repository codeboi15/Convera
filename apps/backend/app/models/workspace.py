from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.models.enums import Role


class Workspace(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(120), unique=True, index=True, nullable=False
    )
    # Custom domain for the public knowledge base (e.g. help.acme.com).
    custom_domain: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, index=True
    )
    custom_domain_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    # Random token the owner publishes as a DNS TXT record to prove control of
    # the domain before we will serve content on it.
    custom_domain_token: Mapped[Optional[str]] = mapped_column(String(64))
    custom_domain_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    # Certificate state reported by the configured domain provider:
    # none | pending | active | error
    custom_domain_ssl_status: Mapped[str] = mapped_column(
        String(20), default="none", server_default="none", nullable=False
    )

    # Inbound email routing. Incoming mail is addressed to
    # ``<mailbox>+<inbound_key>@<domain>`` and the plus-tag selects the tenant,
    # so one mailbox (or one Postmark server) serves every workspace.
    inbound_key: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    # Where the workspace forwards its real support address from, used as
    # Reply-To so customers keep replying to their own branded address.
    support_email: Mapped[Optional[str]] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(
        String(50), default="free", server_default="free", nullable=False
    )


class WorkspaceMember(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "workspace_members"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, name="role"), default=Role.agent, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_member_workspace_user"),
    )


class Invite(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "invites"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, name="role"), default=Role.agent, nullable=False
    )
    token: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, nullable=False
    )
    invited_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
