from __future__ import annotations

import logging
from typing import Dict, Optional

import httpx

from app.core.config import settings
from app.services.email.base import EmailProvider, OutboundEmail
from app.services.email.routing import normalize_message_id

logger = logging.getLogger(__name__)

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


def _split_address(value: str) -> Dict[str, str]:
    """Turn ``Name <a@b.com>`` or ``a@b.com`` into Brevo's {name,email} shape."""
    value = (value or "").strip()
    if "<" in value and value.endswith(">"):
        name, _, addr = value.partition("<")
        return {"name": name.strip().strip('"'), "email": addr[:-1].strip()}
    return {"email": value}


class BrevoProvider(EmailProvider):
    """Outbound email over HTTPS via Brevo.

    Chosen because several hosting platforms block outbound SMTP entirely —
    on Railway, connections to both 587 and 465 fail with ``Network is
    unreachable``. An HTTPS API is unaffected, and Brevo verifies a single
    sender address rather than a whole domain, so it works without owning one.

    Outbound only: inbound still arrives over IMAP, so this provider is paired
    with the polling provider rather than replacing it.
    """

    name = "brevo"

    @property
    def supports_polling(self) -> bool:
        return False

    async def send(self, message: OutboundEmail) -> Optional[str]:
        api_key = settings.brevo_api_key
        sender = message.from_email or settings.brevo_from_email
        if not api_key or not sender:
            logger.warning(
                "Brevo not configured (api_key=%s sender=%s); dropping outbound email",
                bool(api_key),
                bool(sender),
            )
            return None

        payload: Dict[str, object] = {
            "sender": {
                "email": sender,
                **({"name": message.from_name} if message.from_name else {}),
            },
            "to": [_split_address(message.to_email)],
            "subject": message.subject,
            "textContent": message.text_body or "",
        }
        if message.html_body:
            payload["htmlContent"] = message.html_body
        if message.reply_to:
            payload["replyTo"] = _split_address(message.reply_to)

        # RFC 5322 threading — this is what keeps the reply in the customer's
        # existing mail thread instead of starting a new one.
        headers: Dict[str, str] = {}
        if message.in_reply_to:
            headers["In-Reply-To"] = message.in_reply_to
        if message.references:
            headers["References"] = " ".join(message.references)
        if headers:
            payload["headers"] = headers

        try:
            async with httpx.AsyncClient(timeout=25) as client:
                res = await client.post(
                    BREVO_SEND_URL,
                    json=payload,
                    headers={
                        "api-key": api_key,
                        "content-type": "application/json",
                        "accept": "application/json",
                    },
                )
        except httpx.HTTPError:
            logger.exception("Brevo request failed")
            return None

        if res.status_code >= 400:
            logger.error(
                "Brevo rejected the message (%s): %s", res.status_code, res.text[:300]
            )
            return None

        try:
            message_id = res.json().get("messageId")
        except ValueError:
            message_id = None
        # Brevo returns a real RFC Message-ID; store it so the customer's reply
        # threads back to this conversation.
        return normalize_message_id(message_id) if message_id else None
