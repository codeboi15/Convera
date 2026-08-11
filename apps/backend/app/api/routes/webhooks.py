from __future__ import annotations

import hmac
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.ratelimit import RateLimit
from app.realtime import events
from app.services.email.inbound import process_inbound
from app.services.email.postmark import parse_webhook

logger = logging.getLogger(__name__)

router = APIRouter()

# Generous: legitimate mail bursts are normal, this only stops a flood.
inbound_limit = RateLimit("webhook:inbound", limit=300, window_seconds=60)


def _authorized(token: Optional[str]) -> bool:
    """Shared-secret check on the webhook URL/header.

    Postmark does not sign inbound payloads, so the documented practice is a
    secret in the endpoint. Compared in constant time.
    """
    expected = settings.postmark_inbound_secret
    if not expected:
        return True  # not configured (local/dev)
    return bool(token) and hmac.compare_digest(token, expected)


@router.post(
    "/postmark/inbound",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(inbound_limit)],
)
async def postmark_inbound(
    request: Request,
    token: Optional[str] = None,
    x_inbound_secret: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Receive an inbound email from Postmark and file it into a workspace."""
    if not _authorized(token or x_inbound_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token"
        )

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON payload"
        )

    email = parse_webhook(payload)
    conversation, message = await process_inbound(session, email)
    if conversation is None or message is None:
        # 200 keeps Postmark from retrying mail we can never route.
        return {"status": "ignored", "reason": "unroutable"}

    await session.commit()
    await session.refresh(message)
    await session.refresh(conversation)
    await events.broadcast_message(conversation, message)

    return {
        "status": "ok",
        "conversation_id": str(conversation.id),
        "message_seq": message.seq,
    }
