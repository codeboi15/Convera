from __future__ import annotations

import uuid
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.core.slug import random_suffix, slugify
from app.models.enums import Role
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.auth import WorkspaceMembershipOut


async def get_user_by_email(session: AsyncSession, email: str) -> Optional[User]:
    return await session.scalar(select(User).where(User.email == email.lower()))


async def list_memberships(
    session: AsyncSession, user_id: uuid.UUID
) -> List[WorkspaceMembershipOut]:
    rows = (
        await session.execute(
            select(Workspace, WorkspaceMember.role)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user_id)
            .order_by(Workspace.created_at)
        )
    ).all()
    return [
        WorkspaceMembershipOut(id=ws.id, name=ws.name, slug=ws.slug, role=role)
        for ws, role in rows
    ]


async def get_membership(
    session: AsyncSession, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> Optional[WorkspaceMember]:
    return await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.workspace_id == workspace_id,
        )
    )


async def unique_slug(session: AsyncSession, name: str) -> str:
    base = slugify(name)[:100]
    slug = base
    while await session.scalar(select(Workspace.id).where(Workspace.slug == slug)):
        slug = f"{base}-{random_suffix()}"
    return slug


async def create_user(
    session: AsyncSession, email: str, password: str, name: Optional[str] = None
) -> User:
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        name=name,
    )
    session.add(user)
    await session.flush()
    return user


async def create_workspace_with_owner(
    session: AsyncSession, name: str, owner: User
) -> Workspace:
    workspace = Workspace(name=name, slug=await unique_slug(session, name))
    session.add(workspace)
    await session.flush()
    session.add(
        WorkspaceMember(
            workspace_id=workspace.id, user_id=owner.id, role=Role.admin
        )
    )
    await session.flush()
    return workspace


def issue_tokens(
    user: User, workspace_id: Optional[uuid.UUID], role: Optional[Role]
) -> Tuple[str, str]:
    claims = {}
    if workspace_id is not None:
        claims["ws"] = str(workspace_id)
    if role is not None:
        claims["role"] = role.value
    access = create_access_token(str(user.id), claims=claims)
    refresh = create_refresh_token(str(user.id))
    return access, refresh


async def authenticate(
    session: AsyncSession, email: str, password: str
) -> Optional[User]:
    user = await get_user_by_email(session, email)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
