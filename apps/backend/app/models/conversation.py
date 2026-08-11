from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.models.enums import Channel, ConversationStatus, SenderType


class Conversation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    channel: Mapped[Channel] = mapped_column(
        SAEnum(Channel, name="channel"), nullable=False
    )
    status: Mapped[ConversationStatus] = mapped_column(
        SAEnum(ConversationStatus, name="conversation_status"),
        default=ConversationStatus.open,
        server_default=ConversationStatus.open.value,
        index=True,
        nullable=False,
    )
    subject: Mapped[Optional[str]] = mapped_column(String(500))
    assignee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), index=True
    )
    snoozed_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    message_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    # Email threading: last outbound/inbound Message-ID seen on this thread.
    email_last_message_id: Mapped[Optional[str]] = mapped_column(String(500))

    # AI summary cache.
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    ai_summary_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    ai_summary_message_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )


class Message(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # Monotonic per-conversation ordering key (gap recovery + ordering guarantee).
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_type: Mapped[SenderType] = mapped_column(
        SAEnum(SenderType, name="sender_type"), nullable=False
    )
    sender_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    sender_contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    html: Mapped[Optional[str]] = mapped_column(Text)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Email headers for threading.
    email_message_id: Mapped[Optional[str]] = mapped_column(String(500), index=True)
    email_in_reply_to: Mapped[Optional[str]] = mapped_column(String(500))

    attachments: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "seq", name="uq_message_conversation_seq"
        ),
        # Idempotent inbound email: re-polling the mailbox or a webhook retry
        # can never create the same message twice.
        Index(
            "uq_message_workspace_email_id",
            "workspace_id",
            "email_message_id",
            unique=True,
            postgresql_where=text("email_message_id IS NOT NULL"),
        ),
    )
