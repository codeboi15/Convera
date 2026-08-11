from __future__ import annotations

import logging
from typing import Optional, Tuple

import bleach
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.enums import Channel, ConversationStatus, SenderType
from app.models.workspace import Workspace
from app.services import conversation as convo_service
from app.services.email.base import InboundEmail
from app.services.email.routing import first_inbound_key, normalize_message_id

logger = logging.getLogger(__name__)

# Email HTML is untrusted: strip scripts/styles/handlers before it is ever
# rendered in the agent dashboard.
ALLOWED_TAGS = [
    "p", "br", "div", "span", "a", "b", "strong", "i", "em", "u", "ul", "ol",
    "li", "blockquote", "pre", "code", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "td", "th", "hr", "img",
]
ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "width", "height"],
}


def sanitize_html(html: Optional[str]) -> Optional[str]:
    if not html:
        return None
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=["http", "https", "mailto", "cid", "data"],
        strip=True,
    )


async def resolve_workspace(
    session: AsyncSession, email: InboundEmail
) -> Optional[Workspace]:
    """Find the tenant this email belongs to.

    Preference order:
      1. the plus-tag on a recipient address
      2. the thread it replies to (survives forwarders that strip the tag)
    """
    key = first_inbound_key(email.recipient_candidates())
    if key:
        workspace = await session.scalar(
            select(Workspace).where(Workspace.inbound_key == key)
        )
        if workspace is not None:
            return workspace
        logger.warning("inbound email for unknown workspace key=%r", key)

    thread_ids = [
        normalize_message_id(m)
        for m in ([email.in_reply_to] if email.in_reply_to else []) + email.references
    ]
    thread_ids = [m for m in thread_ids if m]
    if thread_ids:
        message = await session.scalar(
            select(Message).where(Message.email_message_id.in_(thread_ids))
        )
        if message is not None:
            return await session.get(Workspace, message.workspace_id)

    return None


async def find_thread_conversation(
    session: AsyncSession, workspace_id, email: InboundEmail
) -> Optional[Conversation]:
    """Locate the existing conversation via RFC 5322 threading headers."""
    candidates = [
        normalize_message_id(m)
        for m in ([email.in_reply_to] if email.in_reply_to else []) + email.references
    ]
    candidates = [m for m in candidates if m]
    if not candidates:
        return None

    message = await session.scalar(
        select(Message)
        .where(
            Message.workspace_id == workspace_id,
            Message.email_message_id.in_(candidates),
        )
        .order_by(Message.created_at.desc())
    )
    if message is None:
        return None
    return await session.get(Conversation, message.conversation_id)


async def get_or_create_contact(
    session: AsyncSession, workspace_id, email: InboundEmail
) -> Contact:
    address = (email.from_email or "").lower()
    contact = await session.scalar(
        select(Contact).where(
            Contact.workspace_id == workspace_id, Contact.email == address
        )
    )
    if contact is None:
        contact = Contact(
            workspace_id=workspace_id, email=address, name=email.from_name
        )
        session.add(contact)
        await session.flush()
    elif email.from_name and not contact.name:
        contact.name = email.from_name
    return contact


async def process_inbound(
    session: AsyncSession, email: InboundEmail
) -> Tuple[Optional[Conversation], Optional[Message]]:
    """Turn a received email into a message on the right conversation.

    Idempotent: a repeated Message-ID (webhook retry, mailbox re-poll) is
    ignored rather than duplicated.
    """
    workspace = await resolve_workspace(session, email)
    if workspace is None:
        logger.warning(
            "dropping unroutable inbound email message_id=%s to=%s",
            email.message_id,
            email.to,
        )
        return None, None

    message_id = normalize_message_id(email.message_id)
    if message_id:
        existing = await session.scalar(
            select(Message).where(
                Message.workspace_id == workspace.id,
                Message.email_message_id == message_id,
            )
        )
        if existing is not None:
            logger.info("skipping duplicate inbound email %s", message_id)
            return (
                await session.get(Conversation, existing.conversation_id),
                existing,
            )

    contact = await get_or_create_contact(session, workspace.id, email)

    conversation = await find_thread_conversation(session, workspace.id, email)
    if conversation is None:
        conversation = Conversation(
            workspace_id=workspace.id,
            contact_id=contact.id,
            channel=Channel.email,
            status=ConversationStatus.open,
            subject=(email.subject or "(no subject)")[:500],
        )
        session.add(conversation)
        await session.flush()

    message = await convo_service.add_message(
        session,
        workspace_id=workspace.id,
        conversation=conversation,
        sender_type=SenderType.contact,
        body=email.text_body or "",
        html=sanitize_html(email.html_body),
        sender_contact_id=contact.id,
        email_message_id=message_id,
        email_in_reply_to=normalize_message_id(email.in_reply_to),
    )
    # Remember the newest header so our replies thread correctly.
    conversation.email_last_message_id = message_id

    return conversation, message
