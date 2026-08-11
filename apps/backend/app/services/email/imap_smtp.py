from __future__ import annotations

import asyncio
import email as email_lib
import imaplib
import logging
import smtplib
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from typing import List, Optional

from app.core.config import settings
from app.services.email.base import EmailProvider, InboundEmail, OutboundEmail
from app.services.email.routing import normalize_message_id, parse_references

logger = logging.getLogger(__name__)


def _decode(value: Optional[str]) -> str:
    """Decode RFC 2047 encoded headers (=?utf-8?B?...?=) to plain text."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # pragma: no cover - malformed header
        return value


def _body_parts(msg: email_lib.message.Message) -> tuple:
    """Extract (text, html) from a possibly multipart message."""
    text: Optional[str] = None
    html: Optional[str] = None

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_filename():  # attachment
                continue
            ctype = part.get_content_type()
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
            except Exception:  # pragma: no cover
                continue
            if ctype == "text/plain" and text is None:
                text = decoded
            elif ctype == "text/html" and html is None:
                html = decoded
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace") if payload else ""
        except Exception:  # pragma: no cover
            decoded = ""
        if msg.get_content_type() == "text/html":
            html = decoded
        else:
            text = decoded

    return text or "", html


def parse_message(raw: bytes) -> InboundEmail:
    """Convert a raw RFC 822 message into the normalised inbound shape."""
    msg = email_lib.message_from_bytes(raw)
    from_name, from_email = parseaddr(_decode(msg.get("From")))
    text, html = _body_parts(msg)

    def addr_list(header: str) -> List[str]:
        raw_value = _decode(msg.get(header))
        if not raw_value:
            return []
        return [a.strip() for a in raw_value.split(",") if a.strip()]

    return InboundEmail(
        message_id=normalize_message_id(msg.get("Message-ID")) or "",
        from_email=(from_email or "").lower(),
        from_name=from_name or None,
        to=addr_list("To"),
        cc=addr_list("Cc"),
        subject=_decode(msg.get("Subject")),
        text_body=text,
        html_body=html,
        in_reply_to=normalize_message_id(msg.get("In-Reply-To")),
        references=parse_references(msg.get("References")),
        # Gmail stamps the true delivery address here, plus-tag intact.
        delivered_to=_decode(msg.get("Delivered-To")) or None,
    )


class ImapSmtpProvider(EmailProvider):
    """Plain mailbox transport: IMAP for inbound, SMTP for outbound.

    Works with any mailbox (Gmail, Zoho, Fastmail) with no provider approval
    and no domain of your own — multi-tenancy comes from plus-addressing.
    """

    name = "imap"

    @property
    def supports_polling(self) -> bool:
        return True

    # ── Inbound ─────────────────────────────────────────────────────────
    def _fetch_sync(self) -> List[InboundEmail]:
        if not settings.imap_username or not settings.imap_password:
            return []

        messages: List[InboundEmail] = []
        client = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
        try:
            client.login(settings.imap_username, settings.imap_password)
            client.select("INBOX")
            status, data = client.search(None, "UNSEEN")
            if status != "OK":
                return []

            for num in data[0].split():
                status, payload = client.fetch(num, "(RFC822)")
                if status != "OK" or not payload or not payload[0]:
                    continue
                try:
                    messages.append(parse_message(payload[0][1]))
                except Exception:
                    logger.exception("could not parse inbound message")
                    continue
                # Mark seen so the next poll skips it; the Message-ID unique
                # index is the real safeguard against duplicates.
                client.store(num, "+FLAGS", "\\Seen")
        finally:
            try:
                client.logout()
            except Exception:  # pragma: no cover
                pass

        return messages

    async def fetch(self) -> List[InboundEmail]:
        try:
            return await asyncio.to_thread(self._fetch_sync)
        except Exception:
            logger.exception("IMAP poll failed")
            return []

    # ── Outbound ────────────────────────────────────────────────────────
    def _send_sync(self, message: OutboundEmail) -> Optional[str]:
        sender = message.from_email or settings.smtp_username
        if not sender or not settings.smtp_password:
            logger.warning("SMTP not configured; dropping outbound email")
            return None

        msg = EmailMessage()
        msg["Message-ID"] = make_msgid()
        msg["From"] = formataddr(
            (message.from_name or settings.email_from_name, sender)
        )
        msg["To"] = message.to_email
        msg["Subject"] = message.subject
        if message.reply_to:
            msg["Reply-To"] = message.reply_to
        # Threading: these two headers are what keep the reply in the
        # customer's existing mail thread.
        if message.in_reply_to:
            msg["In-Reply-To"] = message.in_reply_to
        if message.references:
            msg["References"] = " ".join(message.references)

        msg.set_content(message.text_body or "")
        if message.html_body:
            msg.add_alternative(message.html_body, subtype="html")

        # Port 465 speaks TLS from the first byte (implicit TLS / SMTPS); 587
        # starts plaintext and upgrades with STARTTLS. Some hosts block 587 but
        # leave 465 open, so both are supported.
        port = int(settings.smtp_port)
        try:
            if port == 465:
                with smtplib.SMTP_SSL(
                    settings.smtp_host, port, timeout=30
                ) as s:
                    s.login(settings.smtp_username or sender, settings.smtp_password)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(settings.smtp_host, port, timeout=30) as s:
                    s.starttls()
                    s.login(settings.smtp_username or sender, settings.smtp_password)
                    s.send_message(msg)
        except OSError as exc:
            # Errno 101/111 here almost always means the platform blocks the
            # SMTP port rather than anything being wrong with the credentials.
            logger.error(
                "SMTP connect to %s:%s failed (%s). If this is a hosted "
                "platform, outbound SMTP ports are often blocked — try "
                "SMTP_PORT=465, or switch EMAIL_PROVIDER to an HTTPS-based "
                "provider.",
                settings.smtp_host,
                port,
                exc,
            )
            raise

        return msg["Message-ID"]

    async def send(self, message: OutboundEmail) -> Optional[str]:
        return await asyncio.to_thread(self._send_sync, message)
