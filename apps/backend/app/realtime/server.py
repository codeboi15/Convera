from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

import socketio

from app.core.config import settings

logger = logging.getLogger(__name__)

# A Redis-backed manager fans messages out across every API instance, so an
# agent connected to instance A still receives a message published by instance B.
_manager = (
    socketio.AsyncRedisManager(settings.redis_url) if settings.redis_url else None
)

sio = socketio.AsyncServer(
    async_mode="asgi",
    client_manager=_manager,
    cors_allowed_origins=settings.cors_origin_list or "*",
    logger=settings.debug,
    engineio_logger=False,
)


async def _session(sid: str) -> Dict[str, Any]:
    try:
        return await sio.get_session(sid) or {}
    except KeyError:  # pragma: no cover - socket already gone
        return {}


@sio.event
async def connect(sid: str, environ: dict, auth: Optional[dict] = None) -> bool:
    """Authenticate a socket as either an agent (JWT) or an end user (widget token).

    Returning False rejects the connection outright, so unauthenticated sockets
    never join a room.
    """
    from app.core.security import decode_token
    from app.realtime import events, presence
    from app.services.widget import decode_widget_token

    auth = auth or {}
    token = auth.get("token")
    if not token:
        logger.debug("socket %s rejected: no token", sid)
        return False

    widget_identity = decode_widget_token(token)
    if widget_identity is not None:
        workspace_id, contact_id = widget_identity
        await sio.save_session(
            sid,
            {
                "kind": "widget",
                "workspace_id": str(workspace_id),
                "contact_id": str(contact_id),
                "actor": f"contact:{contact_id}",
            },
        )
        await sio.enter_room(sid, events.workspace_room(workspace_id))
        await presence.mark_online(str(workspace_id), f"contact:{contact_id}")
        await events.broadcast_presence(workspace_id, None, f"contact:{contact_id}", True)
        return True

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access" or payload.get("kind"):
        logger.debug("socket %s rejected: invalid token", sid)
        return False

    raw_ws = payload.get("ws")
    if not raw_ws:
        return False

    try:
        workspace_id = uuid.UUID(str(raw_ws))
        user_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError, TypeError):
        return False

    await sio.save_session(
        sid,
        {
            "kind": "agent",
            "workspace_id": str(workspace_id),
            "user_id": str(user_id),
            "actor": f"agent:{user_id}",
        },
    )
    await sio.enter_room(sid, events.workspace_room(workspace_id))
    await presence.mark_online(str(workspace_id), f"agent:{user_id}")
    await events.broadcast_presence(workspace_id, None, f"agent:{user_id}", True)

    # Membership is re-checked out of band: the handshake must not wait on a
    # database round-trip, but a revoked member still gets disconnected.
    sio.start_background_task(_verify_membership, sid, user_id, workspace_id)
    return True


async def _verify_membership(
    sid: str, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> None:
    """Confirm the token's workspace claim against live membership."""
    from app.core.db import async_session
    from app.services.auth import get_membership

    try:
        async with async_session() as session:
            membership = await get_membership(session, user_id, workspace_id)
    except Exception:  # pragma: no cover - never leave a socket half-checked
        logger.exception("membership verification failed for %s", sid)
        await sio.disconnect(sid)
        return

    if membership is None:
        logger.info("socket %s disconnected: no longer a workspace member", sid)
        await sio.disconnect(sid)


@sio.event
async def disconnect(sid: str) -> None:
    from app.realtime import events, presence

    sess = await _session(sid)
    workspace_id = sess.get("workspace_id")
    actor = sess.get("actor")
    if workspace_id and actor:
        await presence.mark_offline(workspace_id, actor)
        try:
            await events.broadcast_presence(
                uuid.UUID(workspace_id), None, actor, False
            )
        except (ValueError, TypeError):  # pragma: no cover
            pass


@sio.event
async def heartbeat(sid: str, data: Optional[dict] = None) -> dict:
    """Refresh the presence TTL; clients send this on an interval."""
    from app.realtime import presence

    sess = await _session(sid)
    if sess.get("workspace_id") and sess.get("actor"):
        await presence.heartbeat(sess["workspace_id"], sess["actor"])
    return {"ok": True}


async def _authorize_conversation(
    sess: Dict[str, Any], conversation_id: uuid.UUID
):
    """Load a conversation and confirm this socket may access it."""
    from app.core.db import async_session
    from app.services.conversation import get_conversation

    workspace_id = sess.get("workspace_id")
    if not workspace_id:
        return None, None

    async with async_session() as session:
        conv = await get_conversation(
            session, uuid.UUID(workspace_id), conversation_id
        )
        if conv is None:
            return None, None
        # An end user may only touch their own conversation.
        if sess.get("kind") == "widget" and str(conv.contact_id) != sess.get(
            "contact_id"
        ):
            return None, None
        return conv, session


@sio.event
async def join_conversation(sid: str, data: dict) -> dict:
    """Join a conversation room and replay anything missed since ``last_seq``."""
    from app.realtime import events
    from app.core.db import async_session
    from app.services.conversation import get_conversation, list_messages

    sess = await _session(sid)
    try:
        conversation_id = uuid.UUID(str(data.get("conversation_id")))
    except (ValueError, TypeError):
        return {"ok": False, "error": "invalid conversation_id"}

    workspace_id = sess.get("workspace_id")
    if not workspace_id:
        return {"ok": False, "error": "unauthenticated"}

    async with async_session() as session:
        conv = await get_conversation(
            session, uuid.UUID(workspace_id), conversation_id
        )
        if conv is None:
            return {"ok": False, "error": "not found"}
        if sess.get("kind") == "widget" and str(conv.contact_id) != sess.get(
            "contact_id"
        ):
            return {"ok": False, "error": "forbidden"}

        last_seq = data.get("last_seq")
        missed = []
        if last_seq is not None:
            try:
                missed = await list_messages(
                    session, conv.id, after_seq=int(last_seq)
                )
            except (ValueError, TypeError):
                missed = []

    await sio.enter_room(sid, events.conversation_room(conversation_id))
    return {
        "ok": True,
        "conversation_id": str(conversation_id),
        "missed": [events.serialize_message(m) for m in missed],
    }


@sio.event
async def leave_conversation(sid: str, data: dict) -> dict:
    from app.realtime import events

    try:
        conversation_id = uuid.UUID(str(data.get("conversation_id")))
    except (ValueError, TypeError):
        return {"ok": False}
    await sio.leave_room(sid, events.conversation_room(conversation_id))
    return {"ok": True}


@sio.event
async def send_message(sid: str, data: dict) -> dict:
    """Persist a message, then broadcast it. Persist-first guarantees ordering."""
    from app.core.db import async_session
    from app.models.enums import SenderType
    from app.realtime import events
    from app.services.conversation import add_message, get_conversation

    sess = await _session(sid)
    workspace_id = sess.get("workspace_id")
    if not workspace_id:
        return {"ok": False, "error": "unauthenticated"}

    body = (data.get("body") or "").strip()
    if not body:
        return {"ok": False, "error": "empty message"}
    if len(body) > 20000:
        return {"ok": False, "error": "message too long"}

    try:
        conversation_id = uuid.UUID(str(data.get("conversation_id")))
    except (ValueError, TypeError):
        return {"ok": False, "error": "invalid conversation_id"}

    async with async_session() as session:
        conv = await get_conversation(
            session, uuid.UUID(workspace_id), conversation_id
        )
        if conv is None:
            return {"ok": False, "error": "not found"}

        if sess.get("kind") == "widget":
            if str(conv.contact_id) != sess.get("contact_id"):
                return {"ok": False, "error": "forbidden"}
            message = await add_message(
                session,
                workspace_id=conv.workspace_id,
                conversation=conv,
                sender_type=SenderType.contact,
                body=body,
                sender_contact_id=uuid.UUID(sess["contact_id"]),
            )
        else:
            message = await add_message(
                session,
                workspace_id=conv.workspace_id,
                conversation=conv,
                sender_type=SenderType.agent,
                body=body,
                sender_user_id=uuid.UUID(sess["user_id"]),
            )
        await session.commit()
        await session.refresh(message)
        await session.refresh(conv)
        payload = events.serialize_message(message)
        await events.broadcast_message(conv, message)

    # Echo back so the sender can reconcile its optimistic message.
    return {"ok": True, "message": payload}


@sio.event
async def typing(sid: str, data: dict) -> dict:
    from app.models.enums import SenderType
    from app.realtime import events

    sess = await _session(sid)
    if not sess.get("workspace_id"):
        return {"ok": False}
    try:
        conversation_id = uuid.UUID(str(data.get("conversation_id")))
    except (ValueError, TypeError):
        return {"ok": False}

    sender = (
        SenderType.contact if sess.get("kind") == "widget" else SenderType.agent
    )
    await events.broadcast_typing(
        conversation_id, sender, bool(data.get("is_typing")), skip_sid=sid
    )
    return {"ok": True}


@sio.event
async def mark_read(sid: str, data: dict) -> dict:
    from app.core.db import async_session
    from app.models.enums import SenderType
    from app.realtime import events
    from app.services.conversation import get_conversation, mark_read as do_mark_read

    sess = await _session(sid)
    workspace_id = sess.get("workspace_id")
    if not workspace_id:
        return {"ok": False}
    try:
        conversation_id = uuid.UUID(str(data.get("conversation_id")))
        up_to_seq = int(data.get("up_to_seq", 0))
    except (ValueError, TypeError):
        return {"ok": False}

    reader = SenderType.contact if sess.get("kind") == "widget" else SenderType.agent
    async with async_session() as session:
        conv = await get_conversation(
            session, uuid.UUID(workspace_id), conversation_id
        )
        if conv is None:
            return {"ok": False}
        if sess.get("kind") == "widget" and str(conv.contact_id) != sess.get(
            "contact_id"
        ):
            return {"ok": False}
        updated = await do_mark_read(session, conv.id, reader, up_to_seq)
        await session.commit()
        await events.broadcast_read(conv, reader, up_to_seq)

    return {"ok": True, "updated": updated}
