from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_workspace_context
from app.core.db import get_session
from app.models.enums import Channel, ConversationStatus, SenderType
from app.schemas.conversation import (
    AssignRequest,
    ConversationDetail,
    ConversationListOut,
    ConversationOut,
    MessageOut,
    SendMessageRequest,
    StatusRequest,
)
from app.services import auth as auth_service
from app.services import conversation as convo_service

router = APIRouter()


@router.get("", response_model=ConversationListOut)
async def list_conversations(
    channel: Optional[Channel] = None,
    status_filter: Optional[ConversationStatus] = Query(default=None, alias="status"),
    assignee_id: Optional[uuid.UUID] = None,
    unassigned: bool = False,
    search: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> ConversationListOut:
    items, total = await convo_service.list_conversations(
        session,
        current.workspace_id,
        channel=channel,
        status=status_filter,
        assignee_id=assignee_id,
        unassigned=unassigned,
        search=search,
        limit=limit,
        offset=offset,
    )
    return ConversationListOut(items=items, total=total, limit=limit, offset=offset)


async def _load(
    session: AsyncSession, current: CurrentUser, conversation_id: uuid.UUID
):
    conv = await convo_service.get_conversation(
        session, current.workspace_id, conversation_id
    )
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    return conv


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> ConversationDetail:
    conv = await _load(session, current, conversation_id)
    messages = await convo_service.list_messages(session, conv.id)
    base = await convo_service.to_out(session, conv)
    return ConversationDetail(
        **base.model_dump(),
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.get("/{conversation_id}/messages", response_model=List[MessageOut])
async def list_messages(
    conversation_id: uuid.UUID,
    after_seq: Optional[int] = Query(default=None, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> List[MessageOut]:
    conv = await _load(session, current, conversation_id)
    messages = await convo_service.list_messages(
        session, conv.id, after_seq=after_seq, limit=limit
    )
    return [MessageOut.model_validate(m) for m in messages]


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> MessageOut:
    """Agent reply. Chat replies are pushed over Socket.IO; email replies are
    queued for delivery by the worker (wired in the email-channel step)."""
    conv = await _load(session, current, conversation_id)
    message = await convo_service.add_message(
        session,
        workspace_id=current.workspace_id,
        conversation=conv,
        sender_type=SenderType.agent,
        body=payload.body,
        sender_user_id=current.user.id,
    )
    await session.commit()
    await session.refresh(message)

    from app.realtime import events

    await events.broadcast_message(conv, message)

    # Email replies leave through the worker so a slow SMTP/API call never
    # blocks the agent's request.
    if conv.channel == Channel.email:
        from app.services.email.dispatch import enqueue_reply

        await enqueue_reply(message.id)

    return MessageOut.model_validate(message)


@router.post("/{conversation_id}/assign", response_model=ConversationOut)
async def assign_conversation(
    conversation_id: uuid.UUID,
    payload: AssignRequest,
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> ConversationOut:
    conv = await _load(session, current, conversation_id)

    if payload.assignee_id is not None:
        membership = await auth_service.get_membership(
            session, payload.assignee_id, current.workspace_id
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assignee is not a member of this workspace",
            )

    conv.assignee_id = payload.assignee_id
    await session.commit()
    await session.refresh(conv)

    out = await convo_service.to_out(session, conv)
    from app.realtime import events

    await events.broadcast_conversation_update(conv)
    return out


@router.post("/{conversation_id}/status", response_model=ConversationOut)
async def set_status(
    conversation_id: uuid.UUID,
    payload: StatusRequest,
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> ConversationOut:
    conv = await _load(session, current, conversation_id)

    if payload.status == ConversationStatus.snoozed:
        if payload.snoozed_until is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="snoozed_until is required when snoozing a conversation",
            )
        when = payload.snoozed_until
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="snoozed_until must be in the future",
            )
        conv.snoozed_until = when
    else:
        conv.snoozed_until = None

    conv.status = payload.status
    await session.commit()
    await session.refresh(conv)

    out = await convo_service.to_out(session, conv)
    from app.realtime import events

    await events.broadcast_conversation_update(conv)
    return out


@router.post("/{conversation_id}/read", response_model=dict)
async def mark_read(
    conversation_id: uuid.UUID,
    up_to_seq: int = Query(ge=0),
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    conv = await _load(session, current, conversation_id)
    updated = await convo_service.mark_read(
        session, conv.id, SenderType.agent, up_to_seq
    )
    await session.commit()

    from app.realtime import events

    await events.broadcast_read(conv, SenderType.agent, up_to_seq)
    return {"updated": updated, "up_to_seq": up_to_seq}
