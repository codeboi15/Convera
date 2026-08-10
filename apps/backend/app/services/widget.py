from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, decode_token
from app.models.contact import Contact
from app.models.workspace import Workspace

# End-user sessions are long-lived so a returning visitor keeps their history.
WIDGET_TOKEN_DAYS = 30


def create_widget_token(workspace_id: uuid.UUID, contact_id: uuid.UUID) -> str:
    """Anonymous, workspace-scoped token for an end user.

    Deliberately a different token ``type`` than agent access tokens so a widget
    token can never satisfy a dashboard dependency.
    """
    return create_access_token(
        str(contact_id),
        claims={
            "ws": str(workspace_id),
            "kind": "widget",
            "contact": str(contact_id),
        },
        expires_delta=timedelta(days=WIDGET_TOKEN_DAYS),
    )


def decode_widget_token(token: str) -> Optional[Tuple[uuid.UUID, uuid.UUID]]:
    """Return ``(workspace_id, contact_id)`` for a valid widget token."""
    payload = decode_token(token)
    if payload is None or payload.get("kind") != "widget":
        return None
    try:
        return uuid.UUID(str(payload["ws"])), uuid.UUID(str(payload["contact"]))
    except (KeyError, ValueError, TypeError):
        return None


async def get_workspace_by_slug(
    session: AsyncSession, slug: str
) -> Optional[Workspace]:
    return await session.scalar(select(Workspace).where(Workspace.slug == slug))


async def get_or_create_contact(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    external_id: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
) -> Contact:
    contact = await session.scalar(
        select(Contact).where(
            Contact.workspace_id == workspace_id,
            Contact.external_id == external_id,
        )
    )
    if contact is None:
        contact = Contact(
            workspace_id=workspace_id,
            external_id=external_id,
            name=name,
            email=email,
        )
        session.add(contact)
        await session.flush()
    else:
        if name and not contact.name:
            contact.name = name
        if email and not contact.email:
            contact.email = email

    contact.last_seen_at = datetime.now(timezone.utc)
    await session.flush()
    return contact
