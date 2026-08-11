from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Role
from app.models.user import User
from app.models.workspace import Invite, WorkspaceMember
from app.schemas.team import MemberOut

INVITE_TTL_DAYS = 7


def new_invite_token() -> str:
    return secrets.token_urlsafe(32)


async def list_members(
    session: AsyncSession, workspace_id: uuid.UUID
) -> List[MemberOut]:
    rows = (
        await session.execute(
            select(User, WorkspaceMember)
            .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.created_at)
        )
    ).all()
    return [
        MemberOut(
            user_id=user.id,
            email=user.email,
            name=user.name,
            role=member.role,
            joined_at=member.created_at,
        )
        for user, member in rows
    ]


async def create_invite(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    email: str,
    role: Role,
    invited_by_id: uuid.UUID,
) -> Invite:
    invite = Invite(
        workspace_id=workspace_id,
        email=email.lower(),
        role=role,
        token=new_invite_token(),
        invited_by_id=invited_by_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS),
    )
    session.add(invite)
    await session.flush()
    return invite


async def get_valid_invite(session: AsyncSession, token: str) -> Optional[Invite]:
    invite = await session.scalar(select(Invite).where(Invite.token == token))
    if invite is None or invite.accepted_at is not None:
        return None
    if invite.expires_at <= datetime.now(timezone.utc):
        return None
    return invite


async def count_admins(session: AsyncSession, workspace_id: uuid.UUID) -> int:
    rows = await session.execute(
        select(WorkspaceMember.id).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == Role.admin,
        )
    )
    return len(rows.all())
