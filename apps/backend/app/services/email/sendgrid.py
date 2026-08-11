from __future__ import annotations

import logging
from typing import Dict, List, Optional

import httpx

from app.core.config import settings
from app.services.email.base import EmailProvider, OutboundEmail
from app.services.email.routing import normalize_message_id

logger = logging.getLogger(__name__)

SENDGRID_SEND_URL = "https://api.sendgrid.com/v3/mail/send"


def _address(value: str) -> Dict[str, str]:
    """Turn ``Name <a@b.com>`` or ``a@b.com`` into SendGrid's {email,name} shape."""
    value = (value or "").strip()
    if "<" in value and value.endswith(">"):
        name, _, addr = value.partition("<")
        return {"email": addr[:-1].strip(), "name": name.strip().strip('"')}
    return {"email": value}


class SendGridProvider(EmailProvider):
    """Outbound email over HTTPS via SendGrid.

    Used where the host blocks outbound SMTP — on Railway, connections to both
    587 and 465 fail with ``Network is unreachable``. SendGrid verifies a single
    sender address rather than a whole domain, so it works without owning one,
    and unlike some providers it does not restrict calls by source IP (which
    matters because a platform's outbound IPs rotate between deploys).

    Outbound only: inbound still arrives over IMAP.
    """

    name = "sendgrid"

    @property
    def supports_polling(self) -> bool:
        return False

    async def send(self, message: OutboundEmail) -> Optional[str]:
        api_key = settings.sendgrid_api_key
        sender = message.from_email or settings.sendgrid_from_email
        if not api_key or not sender:
            logger.warning(
                "SendGrid not configured (api_key=%s sender=%s); dropping email",
                bool(api_key),
                bool(sender),
            )
            return None

        content: List[Dict[str, str]] = [
            {"type": "text/plain", "value": message.text_body or ""}
        ]
        if message.html_body:
            content.append({"type": "text/html", "value": message.html_body})

        personalization: Dict[str, object] = {"to": [_address(message.to_email)]}

        payload: Dict[str, object] = {
            "personalizations": [personalization],
            "from": {
                "email": sender,
                **({"name": message.from_name} if message.from_name else {}),
            },
            "subject": message.subject,
            "content": content,
        }
        if message.reply_to:
            payload["reply_to"] = _address(message.reply_to)

        # RFC 5322 threading — keeps the reply inside the customer's existing
        # mail thread rather than starting a new one.
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
                    SENDGRID_SEND_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.HTTPError:
            logger.exception("SendGrid request failed")
            return None

        if res.status_code >= 400:
            logger.error(
                "SendGrid rejected the message (%s): %s",
                res.status_code,
                res.text[:300],
            )
            return None

        # SendGrid returns its id in a header, not the body (202 has no body).
        sent_id = res.headers.get("X-Message-Id")
        if not sent_id:
            return None
        return normalize_message_id(f"{sent_id}@sendgrid.net")
