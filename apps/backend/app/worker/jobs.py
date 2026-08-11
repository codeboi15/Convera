from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select, update

from app.core.logging import request_context

logger = logging.getLogger(__name__)


async def generate_summary(
    ctx: Dict[str, Any], conversation_id: str, request_id: Optional[str] = None
) -> None:
    """Generate/refresh the AI summary for a conversation."""
    from app.core.db import async_session
    from app.services.ai import summarize_conversation

    with request_context(request_id):
        try:
            async with async_session() as session:
                await summarize_conversation(session, uuid.UUID(conversation_id))
        except Exception:
            # Summaries are best-effort; never fail the queue over one.
            logger.exception("generate_summary failed for %s", conversation_id)


async def send_email(
    ctx: Dict[str, Any], message_id: str, request_id: Optional[str] = None
) -> None:
    """Deliver an agent reply over the email channel.

    ``request_id`` is the id of the HTTP request whose agent sent this reply.
    Binding it here is what makes the send attempt greppable alongside the
    click that caused it, across two processes.
    """
    from app.core.db import async_session
    from app.services.email.base import get_outbound_provider
    from app.services.email.outbound import send_reply

    with request_context(request_id):
        attempt = ctx.get("job_try", 1)
        logger.info(
            "send_email START message=%s provider=%s attempt=%s",
            message_id,
            get_outbound_provider().name,
            attempt,
        )
        try:
            async with async_session() as session:
                sent = await send_reply(session, uuid.UUID(message_id))
        except Exception:
            # arq retries the job; the Message-ID unique index keeps it idempotent.
            logger.exception(
                "send_email FAILED message=%s attempt=%s", message_id, attempt
            )
            raise

        logger.info(
            "send_email %s message=%s", "OK" if sent else "SKIPPED", message_id
        )


async def poll_inbox(ctx: Dict[str, Any]) -> int:
    """Fetch new mail and file each message into the right workspace.

    Runs on a short cron so mailbox-based inbound behaves like a push feed.
    """
    from app.core.db import async_session
    from app.realtime import events
    from app.services.email.base import get_provider
    from app.services.email.inbound import process_inbound

    # A cron tick has no caller to inherit an id from, so it mints its own.
    with request_context():
        provider = get_provider()
        if not provider.supports_polling:
            logger.debug("poll_inbox skipped: provider=%s is push-based", provider.name)
            return 0

        emails = await provider.fetch()
        if not emails:
            logger.debug("poll_inbox: no new mail")
            return 0

        logger.info("poll_inbox fetched %d new message(s)", len(emails))

        processed = 0
        for email in emails:
            # Each email is an independent unit of work, so each gets its own
            # id — one customer's mail can be traced without the noise of
            # everything else that arrived in the same batch.
            with request_context() as email_trace:
                try:
                    async with async_session() as session:
                        logger.info(
                            "inbound email message_id=%s from=%s",
                            email.message_id,
                            email.from_email,
                        )
                        conversation, message = await process_inbound(session, email)
                        if conversation is None or message is None:
                            logger.info("inbound email unroutable, dropped")
                            continue
                        await session.commit()
                        await session.refresh(message)
                        await session.refresh(conversation)
                        await events.broadcast_message(conversation, message)
                        processed += 1
                        logger.info(
                            "inbound email filed conversation=%s seq=%s",
                            conversation.id,
                            message.seq,
                        )
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

    with request_context():
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
