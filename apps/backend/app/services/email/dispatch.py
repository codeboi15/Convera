from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


async def enqueue_reply(message_id: uuid.UUID) -> bool:
    """Queue an agent reply for delivery by the worker.

    Falls back to sending inline when Redis is unavailable (local dev), so the
    email channel still works without the worker running.
    """
    try:
        from app.worker.queue import get_queue

        queue = await get_queue()
        await queue.enqueue_job("send_email", str(message_id))
        await queue.close()
        return True
    except Exception:
        logger.warning(
            "queue unavailable; sending message %s inline", message_id, exc_info=True
        )

    try:
        from app.core.db import async_session
        from app.services.email.outbound import send_reply

        async with async_session() as session:
            await send_reply(session, message_id)
        return True
    except Exception:
        logger.exception("inline email send failed for %s", message_id)
        return False
