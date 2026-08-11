from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import select, update

logger = logging.getLogger(__name__)


async def generate_summary(ctx: Dict[str, Any], conversation_id: str) -> None:
    """Generate/refresh an AI summary for a conversation (implemented later)."""
    logger.info("generate_summary queued for conversation=%s", conversation_id)


async def send_email(ctx: Dict[str, Any], message_id: str) -> None:
    """Deliver an agent reply over the email channel."""
    from app.core.db import async_session
    from app.services.email.outbound import send_reply

    try:
        async with async_session() as session:
            await send_reply(session, uuid.UUID(message_id))
    except Exception:
        # arq retries the job; the Message-ID unique index keeps it idempotent.
        logger.exception("send_email failed for message=%s", message_id)
        raise


async def poll_inbox(ctx: Dict[str, Any]) -> int:
    """Fetch new mail and file each message into the right workspace.

    Runs on a short cron so mailbox-based inbound behaves like a push feed.
    """
    from app.core.db import async_session
    from app.realtime import events
    from app.services.email.base import get_provider
    from app.services.email.inbound import process_inbound

    provider = get_provider()
    if not provider.supports_polling:
        return 0

    emails = await provider.fetch()
    if not emails:
        return 0

    processed = 0
    for email in emails:
        try:
            async with async_session() as session:
                conversation, message = await process_inbound(session, email)
                if conversation is None or message is None:
                    continue
                await session.commit()
                await session.refresh(message)
                await session.refresh(conversation)
                await events.broadcast_message(conversation, message)
                processed += 1
        except Exception:
            logger.exception(
                "failed to process inbound email %s", email.message_id
            )

    logger.info("poll_inbox processed %d/%d messages", processed, len(emails))
    return processed


async def reopen_snoozed(ctx: Dict[str, Any]) -> int:
    """Return conversations to the open queue once their snooze elapses."""
    from app.core.db import async_session
    from app.models.conversation import Conversation
    from app.models.enums import ConversationStatus

    now = datetime.now(timezone.utc)
    async with async_session() as session:
        result = await session.execute(
            update(Conversation)
            .where(
                Conversation.status == ConversationStatus.snoozed,
                Conversation.snoozed_until.isnot(None),
                Conversation.snoozed_until <= now,
            )
            .values(status=ConversationStatus.open, snoozed_until=None)
        )
        await session.commit()
    count = result.rowcount or 0
    if count:
        logger.info("reopened %d snoozed conversations", count)
    return count
