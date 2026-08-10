from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def generate_summary(ctx: Dict[str, Any], conversation_id: str) -> None:
    """Generate/refresh an AI summary for a conversation (implemented later)."""
    logger.info("generate_summary queued for conversation=%s", conversation_id)


async def send_email(ctx: Dict[str, Any], message_id: str) -> None:
    """Send an outbound email via Postmark with threading headers (later)."""
    logger.info("send_email queued for message=%s", message_id)


async def reopen_snoozed(ctx: Dict[str, Any]) -> None:
    """Cron-style job to reopen conversations whose snooze has elapsed (later)."""
    logger.debug("reopen_snoozed tick")
