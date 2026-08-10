from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.workspace import Workspace
from app.services.email.base import OutboundEmail, get_provider
from app.services.email.routing import (
    inbound_address_for,
    normalize_message_id,
    reply_subject,
)

logger = logging.getLogger(__name__)


async def build_reply(
    session: AsyncSession, message: Message
) -> Optional[OutboundEmail]:
    """Assemble an agent reply as a correctly threaded email."""
    conversation = await session.get(Conversation, message.conversation_id)
    if conversation is None:
        return None
    contact = await session.get(Contact, conversation.contact_id)
    if contact is None or not contact.email:
        logger.warning("conversation %s has no contact email", conversation.id)
        return None
    workspace = await session.get(Workspace, conversation.workspace_id)
    if workspace is None:
        return None

    # Thread against the newest inbound Message-ID and carry the chain forward.
    parent_id = conversation.email_last_message_id
    references: List[str] = []
    prior = (
        await session.scalars(
            select(Message.email_message_id)
            .where(
                Message.conversation_id == conversation.id,
                Message.email_message_id.isnot(None),
            )
            .order_by(Message.seq)
        )
    ).all()
    references = [normalize_message_id(p) for p in prior if p]

    return OutboundEmail(
        to_email=contact.email,
        subject=reply_subject(conversation.subject),
        text_body=message.body,
        html_body=message.html,
        from_name=workspace.name,
        # Send from the workspace's own routing address so customer replies
        # come straight back into this workspace.
        from_email=None,
        reply_to=workspace.support_email
        or inbound_address_for(workspace.inbound_key),
        in_reply_to=parent_id,
        references=references or ([parent_id] if parent_id else None),
    )


async def send_reply(session: AsyncSession, message_id: uuid.UUID) -> bool:
    """Send a stored agent message over the email channel."""
    message = await session.get(Message, message_id)
    if message is None:
        logger.warning("outbound email: message %s not found", message_id)
        return False

    payload = await build_reply(session, message)
    if payload is None:
        return False

    sent_id = await get_provider().send(payload)
    if sent_id:
        # Record our own Message-ID so the customer's reply threads back.
        message.email_message_id = sent_id
        conversation = await session.get(Conversation, message.conversation_id)
        if conversation is not None:
            conversation.email_last_message_id = sent_id
        await session.commit()
    return True
