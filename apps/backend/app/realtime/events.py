from __future__ import annotations

import logging
import uuid
from typing import Optional

from app.models.conversation import Conversation, Message
from app.models.enums import SenderType
from app.realtime.server import sio

logger = logging.getLogger(__name__)


def conversation_room(conversation_id: uuid.UUID) -> str:
    """Room joined by both the end-user widget and any agent viewing the thread."""
    return f"conversation:{conversation_id}"


def workspace_room(workspace_id: uuid.UUID) -> str:
    """Room joined by every agent of a workspace, for inbox-level updates."""
    return f"workspace:{workspace_id}"


def serialize_message(message: Message) -> dict:
    return {
        "id": str(message.id),
        "conversation_id": str(message.conversation_id),
        "seq": message.seq,
        "sender_type": message.sender_type.value,
        "sender_user_id": (
            str(message.sender_user_id) if message.sender_user_id else None
        ),
        "sender_contact_id": (
            str(message.sender_contact_id) if message.sender_contact_id else None
        ),
        "body": message.body,
        "html": message.html,
        "read_at": message.read_at.isoformat() if message.read_at else None,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


async def broadcast_message(conversation: Conversation, message: Message) -> None:
    """Fan out a new message to the thread and to the workspace inbox.

    Emitting through the Socket.IO Redis manager means every API instance
    delivers it to its own connected clients.
    """
    payload = serialize_message(message)
    try:
        await sio.emit(
            "message:new", payload, room=conversation_room(conversation.id)
        )
        await sio.emit(
            "inbox:message",
            {
                "conversation_id": str(conversation.id),
                "channel": conversation.channel.value,
                "status": conversation.status.value,
                "last_message_at": (
                    conversation.last_message_at.isoformat()
                    if conversation.last_message_at
                    else None
                ),
                "preview": message.body[:140],
                "sender_type": message.sender_type.value,
            },
            room=workspace_room(conversation.workspace_id),
        )
    except Exception:  # pragma: no cover - realtime must never break the request
        logger.exception("failed to broadcast message %s", message.id)


async def broadcast_conversation_update(conversation: Conversation) -> None:
    payload = {
        "conversation_id": str(conversation.id),
        "status": conversation.status.value,
        "assignee_id": (
            str(conversation.assignee_id) if conversation.assignee_id else None
        ),
        "snoozed_until": (
            conversation.snoozed_until.isoformat()
            if conversation.snoozed_until
            else None
        ),
    }
    try:
        await sio.emit(
            "conversation:updated",
            payload,
            room=workspace_room(conversation.workspace_id),
        )
        await sio.emit(
            "conversation:updated",
            payload,
            room=conversation_room(conversation.id),
        )
    except Exception:  # pragma: no cover
        logger.exception("failed to broadcast update for %s", conversation.id)


async def broadcast_typing(
    conversation_id: uuid.UUID, sender_type: SenderType, is_typing: bool, skip_sid: Optional[str] = None
) -> None:
    try:
        await sio.emit(
            "typing",
            {
                "conversation_id": str(conversation_id),
                "sender_type": sender_type.value,
                "is_typing": is_typing,
            },
            room=conversation_room(conversation_id),
            skip_sid=skip_sid,
        )
    except Exception:  # pragma: no cover
        logger.exception("failed to broadcast typing for %s", conversation_id)


async def broadcast_read(
    conversation: Conversation, reader: SenderType, up_to_seq: int
) -> None:
    try:
        await sio.emit(
            "message:read",
            {
                "conversation_id": str(conversation.id),
                "reader": reader.value,
                "up_to_seq": up_to_seq,
            },
            room=conversation_room(conversation.id),
        )
    except Exception:  # pragma: no cover
        logger.exception("failed to broadcast read for %s", conversation.id)


async def broadcast_presence(
    workspace_id: uuid.UUID,
    conversation_id: Optional[uuid.UUID],
    actor: str,
    online: bool,
) -> None:
    payload = {
        "actor": actor,
        "online": online,
        "conversation_id": str(conversation_id) if conversation_id else None,
    }
    try:
        if conversation_id:
            await sio.emit(
                "presence", payload, room=conversation_room(conversation_id)
            )
        await sio.emit("presence", payload, room=workspace_room(workspace_id))
    except Exception:  # pragma: no cover
        logger.exception("failed to broadcast presence")
