from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.enums import Channel, ConversationStatus, SenderType
from app.models.user import User
from app.schemas.conversation import (
    AssigneeOut,
    ContactOut,
    ConversationOut,
    MessageOut,
)


async def get_conversation(
    session: AsyncSession, workspace_id: uuid.UUID, conversation_id: uuid.UUID
) -> Optional[Conversation]:
    """Fetch a conversation, always scoped to the caller's workspace."""
    return await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace_id,
        )
    )


async def next_seq(session: AsyncSession, conversation_id: uuid.UUID) -> int:
    """Allocate the next per-conversation sequence number.

    Uses SELECT ... FOR UPDATE on the parent row so concurrent senders cannot
    claim the same ``seq``; combined with the unique (conversation_id, seq)
    constraint this gives a strict, gap-free ordering key.
    """
    current = await session.scalar(
        select(Conversation.message_count)
        .where(Conversation.id == conversation_id)
        .with_for_update()
    )
    return int(current or 0) + 1


async def add_message(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    conversation: Conversation,
    sender_type: SenderType,
    body: str,
    html: Optional[str] = None,
    sender_user_id: Optional[uuid.UUID] = None,
    sender_contact_id: Optional[uuid.UUID] = None,
    email_message_id: Optional[str] = None,
    email_in_reply_to: Optional[str] = None,
) -> Message:
    seq = await next_seq(session, conversation.id)
    now = datetime.now(timezone.utc)

    message = Message(
        workspace_id=workspace_id,
        conversation_id=conversation.id,
        seq=seq,
        sender_type=sender_type,
        sender_user_id=sender_user_id,
        sender_contact_id=sender_contact_id,
        body=body,
        html=html,
        email_message_id=email_message_id,
        email_in_reply_to=email_in_reply_to,
    )
    session.add(message)

    conversation.message_count = seq
    conversation.last_message_at = now
    # Any new activity pulls a snoozed conversation back into the open queue.
    if conversation.status == ConversationStatus.snoozed:
        conversation.status = ConversationStatus.open
        conversation.snoozed_until = None

    await session.flush()
    return message


async def list_messages(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    after_seq: Optional[int] = None,
    limit: int = 200,
) -> List[Message]:
    """Messages in strict ``seq`` order; ``after_seq`` powers reconnect gap recovery."""
    stmt = select(Message).where(Message.conversation_id == conversation_id)
    if after_seq is not None:
        stmt = stmt.where(Message.seq > after_seq)
    stmt = stmt.order_by(Message.seq).limit(limit)
    return list((await session.scalars(stmt)).all())


async def get_or_create_chat_conversation(
    session: AsyncSession, workspace_id: uuid.UUID, contact: Contact
) -> Conversation:
    """Return the contact's open chat conversation, creating one if needed."""
    conversation = await session.scalar(
        select(Conversation)
        .where(
            Conversation.workspace_id == workspace_id,
            Conversation.contact_id == contact.id,
            Conversation.channel == Channel.chat,
            Conversation.status != ConversationStatus.resolved,
        )
        .order_by(Conversation.created_at.desc())
    )
    if conversation is not None:
        return conversation

    conversation = Conversation(
        workspace_id=workspace_id,
        contact_id=contact.id,
        channel=Channel.chat,
        status=ConversationStatus.open,
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def mark_read(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    reader: SenderType,
    up_to_seq: int,
) -> int:
    """Mark the other party's messages as read up to ``up_to_seq``."""
    counterpart = (
        SenderType.contact if reader != SenderType.contact else SenderType.agent
    )
    result = await session.execute(
        update(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.sender_type == counterpart,
            Message.seq <= up_to_seq,
            Message.read_at.is_(None),
        )
        .values(read_at=datetime.now(timezone.utc))
    )
    return result.rowcount or 0


async def list_conversations(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    channel: Optional[Channel] = None,
    status: Optional[ConversationStatus] = None,
    assignee_id: Optional[uuid.UUID] = None,
    unassigned: bool = False,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[ConversationOut], int]:
    assignee = aliased(User)
    stmt = (
        select(Conversation, Contact, assignee)
        .join(Contact, Contact.id == Conversation.contact_id)
        .outerjoin(assignee, assignee.id == Conversation.assignee_id)
        .where(Conversation.workspace_id == workspace_id)
    )

    if channel is not None:
        stmt = stmt.where(Conversation.channel == channel)
    if status is not None:
        stmt = stmt.where(Conversation.status == status)
    if unassigned:
        stmt = stmt.where(Conversation.assignee_id.is_(None))
    elif assignee_id is not None:
        stmt = stmt.where(Conversation.assignee_id == assignee_id)
    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.where(
            func.lower(func.coalesce(Conversation.subject, "")).like(term)
            | func.lower(func.coalesce(Contact.name, "")).like(term)
            | func.lower(func.coalesce(Contact.email, "")).like(term)
        )

    total = await session.scalar(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    )

    stmt = stmt.order_by(
        func.coalesce(Conversation.last_message_at, Conversation.created_at).desc()
    ).limit(limit).offset(offset)

    rows = (await session.execute(stmt)).all()
    conversations = [r[0] for r in rows]

    previews = await _last_message_previews(session, [c.id for c in conversations])
    unread = await _unread_counts(session, [c.id for c in conversations])

    items = [
        _to_out(conv, contact, user, previews.get(conv.id), unread.get(conv.id, 0))
        for conv, contact, user in rows
    ]
    return items, int(total or 0)


async def _last_message_previews(
    session: AsyncSession, conversation_ids: Sequence[uuid.UUID]
) -> dict:
    if not conversation_ids:
        return {}
    latest = (
        select(
            Message.conversation_id,
            func.max(Message.seq).label("max_seq"),
        )
        .where(Message.conversation_id.in_(conversation_ids))
        .group_by(Message.conversation_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(Message.conversation_id, Message.body).join(
                latest,
                (Message.conversation_id == latest.c.conversation_id)
                & (Message.seq == latest.c.max_seq),
            )
        )
    ).all()
    return {cid: (body or "")[:140] for cid, body in rows}


async def _unread_counts(
    session: AsyncSession, conversation_ids: Sequence[uuid.UUID]
) -> dict:
    """Count inbound (contact) messages an agent has not read yet."""
    if not conversation_ids:
        return {}
    rows = (
        await session.execute(
            select(Message.conversation_id, func.count())
            .where(
                Message.conversation_id.in_(conversation_ids),
                Message.sender_type == SenderType.contact,
                Message.read_at.is_(None),
            )
            .group_by(Message.conversation_id)
        )
    ).all()
    return {cid: int(count) for cid, count in rows}


def _to_out(
    conv: Conversation,
    contact: Contact,
    assignee: Optional[User],
    preview: Optional[str] = None,
    unread: int = 0,
) -> ConversationOut:
    return ConversationOut(
        id=conv.id,
        channel=conv.channel,
        status=conv.status,
        subject=conv.subject,
        contact=ContactOut.model_validate(contact),
        assignee=(
            AssigneeOut(id=assignee.id, name=assignee.name, email=assignee.email)
            if assignee is not None
            else None
        ),
        last_message_at=conv.last_message_at,
        snoozed_until=conv.snoozed_until,
        message_count=conv.message_count,
        ai_summary=conv.ai_summary,
        ai_summary_updated_at=conv.ai_summary_updated_at,
        created_at=conv.created_at,
        last_message_preview=preview,
        unread_count=unread,
    )


async def to_out(
    session: AsyncSession, conv: Conversation, unread: int = 0
) -> ConversationOut:
    contact = await session.get(Contact, conv.contact_id)
    assignee = (
        await session.get(User, conv.assignee_id) if conv.assignee_id else None
    )
    return _to_out(conv, contact, assignee, None, unread)


def message_out(message: Message) -> MessageOut:
    return MessageOut.model_validate(message)
