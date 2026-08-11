from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import decode_token
from app.models.enums import Role
from app.models.user import User
from app.models.workspace import WorkspaceMember

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    """The authenticated agent/admin plus their active workspace scope.

    ``workspace_id`` comes from the token's ``ws`` claim and is re-validated
    against ``workspace_members`` on every request, so a stale or forged claim
    cannot grant cross-tenant access.
    """

    user: User
    workspace_id: Optional[uuid.UUID]
    role: Optional[Role]


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    if creds is None or not creds.credentials:
        raise _unauthorized()

    payload = decode_token(creds.credentials)
    if payload is None or payload.get("type") != "access":
        raise _unauthorized("Invalid or expired token")

    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (ValueError, TypeError):
        raise _unauthorized("Invalid token subject")

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("User not found or inactive")

    workspace_id: Optional[uuid.UUID] = None
    role: Optional[Role] = None
    raw_ws = payload.get("ws")
    if raw_ws:
        try:
            candidate = uuid.UUID(str(raw_ws))
        except (ValueError, TypeError):
            raise _unauthorized("Invalid workspace claim")

        membership = await session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == candidate,
                WorkspaceMember.user_id == user.id,
            )
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this workspace",
            )
        workspace_id = membership.workspace_id
        role = membership.role

    return CurrentUser(user=user, workspace_id=workspace_id, role=role)


async def get_workspace_context(
    current: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Require an active workspace scope. Use for all tenant-scoped routes."""
    if current.workspace_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active workspace selected",
        )
    return current


async def require_admin(
    current: CurrentUser = Depends(get_workspace_context),
) -> CurrentUser:
    if current.role != Role.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current
