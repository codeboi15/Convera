from __future__ import annotations

import secrets
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.realtime import presence
from app.schemas.conversation import MessageOut
from app.schemas.widget import WidgetInitRequest, WidgetSession
from app.services import conversation as convo_service
from app.services import widget as widget_service

router = APIRouter()


@router.post("/session", response_model=WidgetSession)
async def init_session(
    payload: WidgetInitRequest, session: AsyncSession = Depends(get_session)
) -> WidgetSession:
    """Bootstrap an end-user chat session.

    Public endpoint: identifies the visitor by an anonymous id, restores their
    open conversation (so history survives a page reload), and returns a
    workspace-scoped token for the realtime connection.
    """
    workspace = await widget_service.get_workspace_by_slug(
        session, payload.workspace_slug
    )
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unknown workspace"
        )

    visitor_id = payload.visitor_id or secrets.token_urlsafe(16)
    contact = await widget_service.get_or_create_contact(
        session,
        workspace_id=workspace.id,
        external_id=visitor_id,
        name=payload.name,
        email=payload.email,
    )
    conversation = await convo_service.get_or_create_chat_conversation(
        session, workspace.id, contact
    )
    await session.commit()
    await session.refresh(conversation)

    messages = await convo_service.list_messages(session, conversation.id)
    token = widget_service.create_widget_token(workspace.id, contact.id)

    return WidgetSession(
        token=token,
        visitor_id=visitor_id,
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        contact_id=contact.id,
        conversation_id=conversation.id,
        messages=[MessageOut.model_validate(m) for m in messages],
        agents_online=await presence.any_agent_online(str(workspace.id)),
    )


def _require_widget_token(authorization: Optional[str]) -> tuple:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing widget token"
        )
    identity = widget_service.decode_widget_token(authorization.split(" ", 1)[1])
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid widget token"
        )
    return identity


@router.get("/messages", response_model=List[MessageOut])
async def widget_messages(
    conversation_id: uuid.UUID,
    after_seq: Optional[int] = Query(default=None, ge=0),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> List[MessageOut]:
    """History / gap recovery for the widget (HTTP fallback when sockets fail)."""
    workspace_id, contact_id = _require_widget_token(authorization)

    conversation = await convo_service.get_conversation(
        session, workspace_id, conversation_id
    )
    if conversation is None or conversation.contact_id != contact_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )

    messages = await convo_service.list_messages(
        session, conversation.id, after_seq=after_seq
    )
    return [MessageOut.model_validate(m) for m in messages]
