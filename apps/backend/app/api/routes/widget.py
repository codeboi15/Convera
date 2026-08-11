from __future__ import annotations

import secrets
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.ratelimit import RateLimit
from app.realtime import presence
from app.schemas.conversation import MessageOut
from app.schemas.kb import ArticleSummary
from app.schemas.widget import WidgetInitRequest, WidgetSession
from app.services import conversation as convo_service
from app.services import kb as kb_service
from app.services import widget as widget_service

router = APIRouter()

# Public and unauthenticated: a visitor can create conversations and query the
# knowledge base without an account, so both need an abuse budget.
session_limit = RateLimit("widget:session", limit=20, window_seconds=60)
suggest_limit = RateLimit("widget:suggest", limit=60, window_seconds=60)


@router.post(
    "/session",
    response_model=WidgetSession,
    dependencies=[Depends(session_limit)],
)
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


@router.get(
    "/suggestions",
    response_model=List[ArticleSummary],
    dependencies=[Depends(suggest_limit)],
)
async def widget_suggestions(
    workspace_slug: str,
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=3, ge=1, le=5),
    session: AsyncSession = Depends(get_session),
) -> List[ArticleSummary]:
    """Published articles matching what the visitor is typing.

    Public and unauthenticated — it only ever returns published content, and
    is what powers self-serve answers inside the chat widget.
    """
    workspace = await widget_service.get_workspace_by_slug(session, workspace_slug)
    if workspace is None:
        return []
    return await kb_service.search_articles(
        session, workspace.id, q, published_only=True, limit=limit
    )


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
